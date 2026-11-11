# -*- coding: utf-8 -*-
"""PrimeTech - passerelle de pointeuse ZKTeco.

Installé sur un ou plusieurs PC du site, ce programme lit la pointeuse sur le
réseau local et envoie ses pointages à Odoo par Internet (HTTPS).  La
pointeuse garde ses pointages en mémoire quand tous les PC sont éteints : ils
sont envoyés, avec leur heure réelle, dès qu'un PC démarre.

Usage :
    primetech_zk_relay.exe            boucle de synchronisation (mode normal)
    primetech_zk_relay.exe --once     une seule synchronisation puis arrêt
    primetech_zk_relay.exe --test     vérifie la pointeuse et Odoo, sans rien envoyer
"""
import argparse
import configparser
import http.cookiejar
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from logging.handlers import RotatingFileHandler

from zk import ZK

VERSION = '1.0.0'
BATCH_SIZE = 2000
LOCK_PORT = 47321  # local port used as a "single instance" lock
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

_logger = logging.getLogger('primetech_zk_relay')


def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging():
    _logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler = RotatingFileHandler(os.path.join(base_dir(), 'passerelle.log'),
                                       maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)
    if sys.stdout is not None:  # no console when started as a background task
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        _logger.addHandler(console)


def load_config():
    path = os.path.join(base_dir(), 'config.ini')
    parser = configparser.ConfigParser()
    if not parser.read(path, encoding='utf-8'):
        raise SystemExit('Fichier de configuration introuvable : %s' % path)
    return {
        'url': parser.get('odoo', 'url').rstrip('/'),
        'database': parser.get('odoo', 'database', fallback='').strip(),
        'token': parser.get('odoo', 'token').strip(),
        'ip': parser.get('pointeuse', 'ip').strip(),
        'port': parser.getint('pointeuse', 'port', fallback=4370),
        'comm_key': parser.getint('pointeuse', 'cle_communication', fallback=0),
        'timeout': parser.getint('pointeuse', 'delai_connexion', fallback=10),
        'interval': parser.getint('passerelle', 'intervalle', fallback=60),
    }


class OdooError(Exception):
    pass


class OdooClient:
    """Minimal HTTP client: database selection cookie + JSON calls."""

    def __init__(self, config):
        self.config = config
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.database_selected = False

    def select_database(self):
        if self.config['database'] and not self.database_selected:
            query = urllib.parse.urlencode({'db': self.config['database']})
            self.opener.open('%s/web/login?%s' % (self.config['url'], query), timeout=30).read()
        self.database_selected = True

    def call(self, operation, payload, retry=True):
        self.select_database()
        request = urllib.request.Request(
            '%s/primetech_biometric/relay/%s' % (self.config['url'], operation),
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer %s' % self.config['token'],
                     'User-Agent': 'PrimeTech-ZK-Relay/%s' % VERSION},
            method='POST')
        try:
            with self.opener.open(request, timeout=120) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read().decode('utf-8')).get('error')
            except ValueError:
                message = None
            if error.code in (400, 404) and retry:
                # Session lost (server restarted, database not selected): select it again.
                self.database_selected = False
                return self.call(operation, payload, retry=False)
            raise OdooError('Odoo a répondu %s : %s' % (error.code, message or error.reason))


class Device:
    def __init__(self, config):
        self.config = config

    def connect(self):
        zk = ZK(self.config['ip'], port=self.config['port'], timeout=self.config['timeout'],
                password=self.config['comm_key'], force_udp=False, ommit_ping=True)
        return zk.connect()

    def read(self, since=None):
        """Return (users, records, info); records are filtered from ``since``."""
        conn = self.connect()
        try:
            conn.disable_device()
            try:
                users = conn.get_users() or []
                attendances = conn.get_attendance() or []
                info = self._info(conn)
            finally:
                conn.enable_device()
        finally:
            conn.disconnect()
        records = []
        for attendance in attendances:
            if not attendance.timestamp:
                continue
            stamp = attendance.timestamp.strftime(TIME_FORMAT)
            if since and stamp < since:
                continue
            records.append({'u': str(attendance.user_id), 't': stamp,
                            's': attendance.status, 'p': attendance.punch})
        users = [{'user_id': str(user.user_id), 'name': user.name, 'uid': user.uid,
                  'privilege': user.privilege, 'card': user.card} for user in users]
        return users, records, info

    @staticmethod
    def _info(conn):
        def safe(method):
            try:
                return method()
            except Exception:
                return None

        info = {
            'device_name': safe(conn.get_device_name),
            'serial': safe(conn.get_serialnumber),
            'firmware': safe(conn.get_firmware_version),
            'platform': safe(conn.get_platform),
            'mac': safe(conn.get_mac),
        }
        if safe(conn.read_sizes) is not None:
            info.update({
                'users': conn.users, 'users_cap': conn.users_cap,
                'fingers': conn.fingers, 'fingers_cap': conn.fingers_cap,
                'faces': conn.faces, 'faces_cap': conn.faces_cap,
                'records': conn.records, 'records_cap': conn.rec_cap,
            })
        device_time = safe(conn.get_time)
        if device_time:
            info['device_time'] = device_time.strftime(TIME_FORMAT)
        return info

    def run_command(self, command):
        name = command.get('name')
        conn = self.connect()
        try:
            if name == 'set_time':
                value = command.get('value')
                target = datetime.strptime(value, TIME_FORMAT) if value else datetime.now()
                conn.set_time(target)
                return 'Heure réglée sur %s.' % target.strftime(TIME_FORMAT)
            if name == 'clear_attendance':
                conn.disable_device()
                try:
                    conn.clear_attendance()
                finally:
                    conn.enable_device()
                return 'Mémoire des pointages vidée.'
            if name == 'restart':
                conn.restart()
                return 'Redémarrage lancé.'
            raise ValueError('Commande inconnue : %s' % name)
        finally:
            if name != 'restart':
                conn.disconnect()


class Relay:
    def __init__(self, config):
        self.config = config
        self.odoo = OdooClient(config)
        self.device = Device(config)
        self.interval = config['interval']
        self.command_results = []

    def agent(self):
        return {'host': socket.gethostname(), 'version': VERSION}

    def cycle(self):
        hello = self.odoo.call('hello', {'agent': self.agent()})
        if not hello.get('ok'):
            raise OdooError(hello.get('error') or 'Réponse invalide.')
        self.interval = hello.get('interval') or self.interval
        users, records, info = self.device.read(hello.get('since'))
        batches = [records[index:index + BATCH_SIZE]
                   for index in range(0, len(records), BATCH_SIZE)] or [[]]
        created, response = 0, {}
        for batch in batches:
            response = self.odoo.call('push', {
                'agent': self.agent(), 'users': users, 'info': info, 'records': batch,
                'command_results': self.command_results,
            })
            if not response.get('ok'):
                raise OdooError(response.get('error') or 'Réponse invalide.')
            self.command_results = []
            created += response.get('created') or 0
        self.interval = response.get('interval') or self.interval
        _logger.info('%s pointage(s) lu(s), %s nouveau(x) dans Odoo%s.', len(records), created,
                     (', identifiants sans employé : %s' % ', '.join(response['unknown']))
                     if response.get('unknown') else '')
        # Commands run after a successful push, so clearing the memory never loses a punch.
        for command in response.get('commands') or []:
            try:
                message = self.device.run_command(command)
                self.command_results.append({'command': command.get('name'), 'ok': True,
                                             'message': message})
                _logger.info('Commande %s : %s', command.get('name'), message)
            except Exception as error:
                self.command_results.append({'command': command.get('name'), 'ok': False,
                                             'message': str(error)})
                _logger.error('Commande %s en échec : %s', command.get('name'), error)
        if self.command_results:
            # Report the command results right away (kept for the next cycle on failure).
            report = self.odoo.call('push', {'agent': self.agent(), 'records': [],
                                             'command_results': self.command_results})
            if report.get('ok'):
                self.command_results = []

    def test(self):
        ok = True
        try:
            users, records, info = self.device.read()
            _logger.info('Pointeuse OK : %s (%s), %s utilisateur(s), %s pointage(s) en mémoire.',
                         info.get('device_name'), info.get('serial'), len(users), len(records))
        except Exception as error:
            ok = False
            _logger.error('Pointeuse injoignable (%s:%s) : %s',
                          self.config['ip'], self.config['port'], error)
        try:
            hello = self.odoo.call('hello', {'agent': self.agent()})
            _logger.info('Odoo OK : pointeuse « %s », synchronisation toutes les %s s.',
                         hello.get('device'), hello.get('interval'))
        except Exception as error:
            ok = False
            _logger.error('Odoo injoignable (%s) : %s', self.config['url'], error)
        return ok

    def run_forever(self):
        delay_on_error = 30
        while True:
            try:
                self.cycle()
                delay_on_error = 30
                time.sleep(self.interval)
            except Exception as error:
                _logger.error('Synchronisation impossible : %s (nouvel essai dans %s s)',
                              error, delay_on_error)
                time.sleep(delay_on_error)
                delay_on_error = min(delay_on_error * 2, 300)


def single_instance_lock():
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(('127.0.0.1', LOCK_PORT))
    except OSError:
        return None
    return lock


def main():
    parser = argparse.ArgumentParser(description='Passerelle de pointeuse PrimeTech')
    parser.add_argument('--once', action='store_true', help='une seule synchronisation')
    parser.add_argument('--test', action='store_true', help='tester la pointeuse et Odoo')
    args = parser.parse_args()
    setup_logging()
    relay = Relay(load_config())
    _logger.info('Passerelle PrimeTech %s démarrée sur %s.', VERSION, socket.gethostname())
    if args.test:
        sys.exit(0 if relay.test() else 1)
    if args.once:
        relay.cycle()
        return
    lock = single_instance_lock()
    if lock is None:
        _logger.info('Une passerelle tourne déjà sur ce PC : arrêt.')
        return
    relay.run_forever()


if __name__ == '__main__':
    main()
