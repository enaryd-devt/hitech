# -*- coding: utf-8 -*-
"""PrimeTech - passerelle de pointeuses ZKTeco.

Installée sur un ou plusieurs PC du site, la passerelle lit les pointeuses sur
le réseau local et envoie leurs pointages à Odoo (« Gestion des pointages »)
par Internet.  La pointeuse garde ses pointages en mémoire quand tous les PC
sont éteints : ils sont envoyés, avec leur heure réelle, dès qu'un PC démarre.

La passerelle tourne en tâche de fond (tâche planifiée « PrimeTech Pointeuse »)
et se pilote depuis une console Web locale : http://localhost:47321

Usage :
    primetech_zk_relay.exe            service (synchronisation + console) ; si le
                                      service tourne déjà, ouvre la console
    primetech_zk_relay.exe --once     une synchronisation de chaque pointeuse
    primetech_zk_relay.exe --test     teste les pointeuses et Odoo
"""
import argparse
import collections
import configparser
import hashlib
import http.cookiejar
import http.server
import ipaddress
import json
import logging
import os
import secrets
import socket
import socketserver
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging.handlers import RotatingFileHandler

from zk import ZK

VERSION = '2.0.0'
UI_PORT = 47321
BATCH_SIZE = 2000
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
CONSOLE_URL = 'http://localhost:%s' % UI_PORT

_logger = logging.getLogger('primetech_zk_relay')


def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def now_str():
    return datetime.now().strftime(TIME_FORMAT)


# ---------------------------------------------------------------------------
# Logging (file + in-memory buffer displayed in the console)
# ---------------------------------------------------------------------------
class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=300):
        super().__init__()
        self.records = collections.deque(maxlen=capacity)

    def emit(self, record):
        self.records.append({'time': datetime.fromtimestamp(record.created).strftime('%d/%m %H:%M:%S'),
                             'level': record.levelname, 'message': record.getMessage()})


MEMORY_LOG = MemoryLogHandler()


def setup_logging():
    _logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler = RotatingFileHandler(os.path.join(base_dir(), 'passerelle.log'),
                                       maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)
    _logger.addHandler(MEMORY_LOG)
    if sys.stdout is not None:  # no console when started as a background task
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        _logger.addHandler(console)


# ---------------------------------------------------------------------------
# Configuration (config.json, migrated from the config.ini of the zip package)
# ---------------------------------------------------------------------------
class Config:
    """Thread-safe JSON configuration shared by the engine and the console."""

    def __init__(self):
        self.path = os.path.join(base_dir(), 'config.json')
        self.lock = threading.RLock()
        self.data = {'version': 2, 'pin_hash': None, 'devices': []}
        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.path):
                with open(self.path, encoding='utf-8') as handle:
                    self.data.update(json.load(handle))
            else:
                self._migrate_ini()

    def _migrate_ini(self):
        ini = os.path.join(base_dir(), 'config.ini')
        parser = configparser.ConfigParser()
        if not parser.read(ini, encoding='utf-8') or not parser.has_section('odoo'):
            return
        self.data['devices'].append({
            'id': uuid.uuid4().hex,
            'name': 'Pointeuse',
            'server_url': parser.get('odoo', 'url').rstrip('/'),
            'database': parser.get('odoo', 'database', fallback='').strip(),
            'token': parser.get('odoo', 'token').strip(),
            'ip': parser.get('pointeuse', 'ip').strip(),
            'port': parser.getint('pointeuse', 'port', fallback=4370),
            'comm_key': parser.getint('pointeuse', 'cle_communication', fallback=0),
            'timeout': parser.getint('pointeuse', 'delai_connexion', fallback=10),
            'enabled': True,
        })
        self.save()
        _logger.info('Configuration importée depuis config.ini.')

    def save(self):
        with self.lock:
            temporary = self.path + '.tmp'
            with open(temporary, 'w', encoding='utf-8') as handle:
                json.dump(self.data, handle, indent=2, ensure_ascii=False)
            os.replace(temporary, self.path)

    def devices(self):
        with self.lock:
            return [dict(device) for device in self.data['devices']]

    def get_device(self, device_id):
        with self.lock:
            return next((dict(device) for device in self.data['devices'] if device['id'] == device_id), None)

    def upsert_device(self, values):
        with self.lock:
            for device in self.data['devices']:
                if device['id'] == values['id']:
                    device.update(values)
                    break
            else:
                self.data['devices'].append(values)
            self.save()

    def remove_device(self, device_id):
        with self.lock:
            self.data['devices'] = [device for device in self.data['devices'] if device['id'] != device_id]
            self.save()

    # -- administrator PIN ------------------------------------------------
    @staticmethod
    def _hash(pin, salt):
        return hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), bytes.fromhex(salt), 120000).hex()

    def set_pin(self, pin):
        with self.lock:
            if pin:
                salt = secrets.token_hex(16)
                self.data['pin_hash'] = '%s$%s' % (salt, self._hash(pin, salt))
            else:
                self.data['pin_hash'] = None
            self.save()

    def check_pin(self, pin):
        stored = self.data.get('pin_hash')
        if not stored:
            return True
        salt, digest = stored.split('$', 1)
        return secrets.compare_digest(self._hash(pin or '', salt), digest)


# ---------------------------------------------------------------------------
# Odoo server
# ---------------------------------------------------------------------------
class OdooError(Exception):
    pass


def _ssl_context():
    return ssl.create_default_context()


def server_candidates(address):
    """Turn what the user typed into candidate base URLs, best first.

    ``hitech.primetechafrik.com`` -> https://..., http://...
    ``38.247.147.212:18077``      -> http://..., https://...
    """
    address = (address or '').strip().rstrip('/')
    if not address:
        return []
    if '://' in address:
        return [address]
    host = address.split('/')[0]
    hostname = host.rsplit(':', 1)[0] if host.count(':') == 1 else host
    try:
        ipaddress.ip_address(hostname.strip('[]'))
        is_ip = True
    except ValueError:
        is_ip = hostname == 'localhost'
    if is_ip or ':' in host:
        return ['http://' + address, 'https://' + address]
    return ['https://' + address, 'http://' + address]


def jsonrpc(url, path, params=None, opener=None, timeout=15):
    body = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params or {}}).encode('utf-8')
    request = urllib.request.Request(url + path, data=body, method='POST',
                                     headers={'Content-Type': 'application/json'})
    open_url = opener.open if opener else urllib.request.urlopen
    with open_url(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('error'):
        raise OdooError(payload['error'].get('data', {}).get('message') or payload['error'].get('message'))
    return payload.get('result')


def check_server(address):
    """Find the Odoo server behind an address; list its databases when allowed."""
    errors = []
    for url in server_candidates(address):
        try:
            info = jsonrpc(url, '/web/webclient/version_info', timeout=10)
        except Exception as error:
            errors.append('%s : %s' % (url, error))
            continue
        try:
            databases = jsonrpc(url, '/web/database/list', timeout=10)
        except Exception:
            databases = None  # database listing disabled on the server
        return {'url': url, 'version': info.get('server_version'), 'databases': databases}
    raise OdooError("Aucun serveur Odoo trouvé à cette adresse. " + ' | '.join(errors))


class OdooClient:
    """HTTP client of one gateway endpoint: database selection cookie + JSON calls."""

    def __init__(self, url, database, token=None):
        self.url = url.rstrip('/')
        self.database = database
        self.token = token
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=_ssl_context()))
        self.database_selected = False

    def select_database(self):
        if self.database and not self.database_selected:
            query = urllib.parse.urlencode({'db': self.database})
            self.opener.open('%s/web/login?%s' % (self.url, query), timeout=30).read()
        self.database_selected = True

    def call(self, operation, payload, retry=True):
        self.select_database()
        headers = {'Content-Type': 'application/json',
                   'User-Agent': 'PrimeTech-ZK-Relay/%s' % VERSION}
        if self.token:
            headers['Authorization'] = 'Bearer %s' % self.token
        request = urllib.request.Request(
            '%s/primetech_biometric/relay/%s' % (self.url, operation),
            data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                result['_latency_ms'] = int((time.monotonic() - started) * 1000)
                return result
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read().decode('utf-8')).get('error')
            except ValueError:
                message = None
            if error.code in (400, 404) and retry:
                # Session lost (server restarted, database not selected): select it again.
                self.database_selected = False
                return self.call(operation, payload, retry=False)
            if error.code == 404:
                message = message or ("le module « Gestion des pointages » n'est pas installé "
                                      "sur cette base")
            raise OdooError('Odoo a répondu %s : %s' % (error.code, message or error.reason))
        except urllib.error.URLError as error:
            raise OdooError('serveur injoignable (%s)' % error.reason)


# ---------------------------------------------------------------------------
# ZKTeco device
# ---------------------------------------------------------------------------
class Device:
    def __init__(self, ip, port=4370, comm_key=0, timeout=10):
        self.ip, self.port, self.comm_key, self.timeout = ip, int(port), int(comm_key or 0), int(timeout)

    def connect(self):
        return ZK(self.ip, port=self.port, timeout=self.timeout, password=self.comm_key,
                  force_udp=False, ommit_ping=True).connect()

    def read(self, since=None):
        """Return (users, records, info); records are filtered from ``since``."""
        conn = self.connect()
        try:
            conn.disable_device()
            try:
                users = conn.get_users() or []
                attendances = conn.get_attendance() or []
                info = self.info(conn)
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

    def probe(self):
        conn = self.connect()
        try:
            return self.info(conn)
        finally:
            conn.disconnect()

    @staticmethod
    def info(conn):
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


def local_networks():
    """IPv4 /24 networks of this PC (private addresses only)."""
    addresses = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(('8.8.8.8', 80))  # no packet is sent: only selects the outgoing interface
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass
    networks = []
    for address in sorted(addresses):
        ip = ipaddress.ip_address(address)
        if ip.is_private and not ip.is_loopback:
            network = ipaddress.ip_network('%s/24' % address, strict=False)
            if network not in networks:
                networks.append(network)
    return networks


def scan_devices(port=4370):
    """Find the ZKTeco devices of the local networks (TCP port 4370 then identification)."""
    def is_open(host):
        try:
            with socket.create_connection((str(host), port), timeout=0.4):
                return str(host)
        except OSError:
            return None

    hosts = [host for network in local_networks() for host in network.hosts()]
    with ThreadPoolExecutor(max_workers=64) as pool:
        candidates = [host for host in pool.map(is_open, hosts) if host]
    found = []
    for host in candidates:
        entry = {'ip': host, 'port': port}
        try:
            info = Device(host, port, 0, 5).probe()
            entry.update(model=info.get('device_name'), serial=info.get('serial'))
        except Exception as error:
            entry['note'] = "port ouvert, identification impossible (clé de communication ?) : %s" % error
        found.append(entry)
    return {'networks': [str(network) for network in local_networks()], 'devices': found}


# ---------------------------------------------------------------------------
# Synchronisation engine
# ---------------------------------------------------------------------------
class DeviceWorker:
    """Synchronisation state of one configured device."""

    def __init__(self, config_values):
        self.config = config_values
        self.client = None
        self.interval = 60
        self.next_run = 0.0
        self.command_results = []
        self.status = {
            'state': 'pending', 'message': 'En attente de la première synchronisation.',
            'last_sync': None, 'last_success': None, 'odoo_device': None,
            'info': {}, 'records_in_memory': None, 'sent_today': 0, 'created_today': 0,
            'today': datetime.now().date().isoformat(), 'latency_ms': None, 'unknown': [],
        }

    def update_config(self, values):
        changed = any(self.config.get(key) != values.get(key)
                      for key in ('server_url', 'database', 'token'))
        self.config = values
        if changed:
            self.client = None
        self.next_run = 0.0

    def odoo(self):
        if self.client is None:
            self.client = OdooClient(self.config['server_url'], self.config.get('database'),
                                     self.config['token'])
        return self.client

    def device(self):
        return Device(self.config['ip'], self.config.get('port', 4370),
                      self.config.get('comm_key', 0), self.config.get('timeout', 10))

    def cycle(self):
        today = datetime.now().date().isoformat()
        if self.status['today'] != today:
            self.status.update(today=today, sent_today=0, created_today=0)
        self.status['last_sync'] = now_str()
        hello = self.odoo().call('hello', {'agent': agent_info()})
        if not hello.get('ok'):
            raise OdooError(hello.get('error') or 'Réponse invalide.')
        self.status['odoo_device'] = hello.get('device')
        self.interval = hello.get('interval') or self.interval
        users, records, info = self.device().read(hello.get('since'))
        self.status['info'] = info
        self.status['records_in_memory'] = info.get('records')
        batches = [records[index:index + BATCH_SIZE]
                   for index in range(0, len(records), BATCH_SIZE)] or [[]]
        created, response = 0, {}
        for batch in batches:
            response = self.odoo().call('push', {
                'agent': agent_info(), 'users': users, 'info': info, 'records': batch,
                'command_results': self.command_results,
            })
            if not response.get('ok'):
                raise OdooError(response.get('error') or 'Réponse invalide.')
            self.command_results = []
            created += response.get('created') or 0
        self.interval = response.get('interval') or self.interval
        self.status.update(latency_ms=response.get('_latency_ms'), unknown=response.get('unknown') or [])
        self.status['sent_today'] += len(records)
        self.status['created_today'] += created
        name = self.config.get('name')
        _logger.info('[%s] %s pointage(s) lu(s), %s nouveau(x) dans Odoo%s.', name, len(records), created,
                     (', identifiants sans employé : %s' % ', '.join(response['unknown']))
                     if response.get('unknown') else '')
        # Commands run after a successful push, so clearing the memory never loses a punch.
        for command in response.get('commands') or []:
            try:
                message = self.device().run_command(command)
                self.command_results.append({'command': command.get('name'), 'ok': True, 'message': message})
                _logger.info('[%s] Commande %s : %s', name, command.get('name'), message)
            except Exception as error:
                self.command_results.append({'command': command.get('name'), 'ok': False,
                                             'message': str(error)})
                _logger.error('[%s] Commande %s en échec : %s', name, command.get('name'), error)
        if self.command_results:
            report = self.odoo().call('push', {'agent': agent_info(), 'records': [],
                                               'command_results': self.command_results})
            if report.get('ok'):
                self.command_results = []
        message = '%s nouveau(x) pointage(s) envoyé(s).' % created if created else 'À jour.'
        if self.status['unknown']:
            message += ' Identifiants sans employé dans Odoo : %s.' % ', '.join(self.status['unknown'])
        self.status.update(state='warning' if self.status['unknown'] else 'ok', message=message,
                           last_success=now_str())

    def run_if_due(self, force=False):
        if not self.config.get('enabled', True):
            self.status.update(state='paused', message='Synchronisation suspendue.')
            return
        if not force and time.monotonic() < self.next_run:
            return
        try:
            self.cycle()
            self.next_run = time.monotonic() + self.interval
        except Exception as error:
            self.status.update(state='error', message=str(error))
            _logger.error('[%s] Synchronisation impossible : %s', self.config.get('name'), error)
            self.next_run = time.monotonic() + min(max(30, self.interval), 120)

    def public_status(self):
        status = dict(self.status)
        status['next_sync_in'] = max(0, int(self.next_run - time.monotonic())) if self.next_run else 0
        status['interval'] = self.interval
        config = {key: value for key, value in self.config.items() if key != 'token'}
        return {'config': config, 'status': status}


def agent_info():
    return {'host': socket.gethostname(), 'version': VERSION}


class Engine:
    def __init__(self, config):
        self.config = config
        self.workers = {}
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.forced = set()
        self.started_at = now_str()
        self.reload()

    def reload(self):
        with self.lock:
            configured = {device['id']: device for device in self.config.devices()}
            for device_id in list(self.workers):
                if device_id not in configured:
                    del self.workers[device_id]
            for device_id, values in configured.items():
                if device_id in self.workers:
                    self.workers[device_id].update_config(values)
                else:
                    self.workers[device_id] = DeviceWorker(values)
        self.wake.set()

    def sync_now(self, device_id=None):
        with self.lock:
            self.forced.update([device_id] if device_id else self.workers.keys())
        self.wake.set()

    def snapshot(self):
        with self.lock:
            return [worker.public_status() for worker in self.workers.values()]

    def run_forever(self):
        while True:
            with self.lock:
                workers = list(self.workers.items())
                forced, self.forced = self.forced, set()
            for device_id, worker in workers:
                worker.run_if_due(force=device_id in forced)
            self.wake.wait(timeout=5)
            self.wake.clear()


# ---------------------------------------------------------------------------
# Local web console
# ---------------------------------------------------------------------------
class ConsoleServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def make_handler(config, engine):
    sessions = set()

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'PrimeTechRelay/%s' % VERSION

        def log_message(self, *args):  # keep the gateway log readable
            pass

        # -- helpers -----------------------------------------------------
        def _send(self, status, body, content_type='application/json; charset=utf-8', headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _host_allowed(self):
            # DNS rebinding protection: the console only answers to localhost names.
            host = (self.headers.get('Host') or '').split(':')[0].lower()
            return host in ('localhost', '127.0.0.1', '[::1]')

        def _session(self):
            cookie = self.headers.get('Cookie') or ''
            for part in cookie.split(';'):
                name, _sep, value = part.strip().partition('=')
                if name == 'pt_relay_session' and value in sessions:
                    return value
            return None

        def _unlocked(self):
            return not config.data.get('pin_hash') or self._session() is not None

        def _body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > 1024 * 1024:
                raise ValueError('requête trop volumineuse')
            return json.loads(self.rfile.read(length) or b'{}')

        # -- routes ------------------------------------------------------
        def do_GET(self):
            if not self._host_allowed():
                return self._send(403, {'error': 'Accès refusé.'})
            if self.path in ('/', '/index.html'):
                return self._send(200, CONSOLE_HTML.encode('utf-8'), 'text/html; charset=utf-8')
            if self.path == '/api/state':
                return self._send(200, {
                    'version': VERSION, 'host': socket.gethostname(), 'started_at': engine.started_at,
                    'has_pin': bool(config.data.get('pin_hash')), 'unlocked': self._unlocked(),
                    'devices': engine.snapshot(), 'logs': list(MEMORY_LOG.records)[-80:],
                })
            return self._send(404, {'error': 'Introuvable.'})

        def do_POST(self):
            # Cross-site protection: browsers cannot send this header from another site
            # without a CORS preflight, which this server never accepts.
            if not self._host_allowed() or self.headers.get('X-PrimeTech-Relay') != '1':
                return self._send(403, {'error': 'Accès refusé.'})
            try:
                payload = self._body()
            except ValueError as error:
                return self._send(400, {'error': str(error)})
            route = self.path.split('?')[0]
            if route == '/api/unlock':
                if not config.check_pin(payload.get('pin')):
                    time.sleep(1)
                    return self._send(403, {'error': 'Code PIN incorrect.'})
                session = secrets.token_urlsafe(24)
                sessions.add(session)
                return self._send(200, {'ok': True}, headers={
                    'Set-Cookie': 'pt_relay_session=%s; HttpOnly; SameSite=Strict; Path=/' % session})
            if route == '/api/sync':
                engine.sync_now(payload.get('id'))
                return self._send(200, {'ok': True})
            if not self._unlocked():
                return self._send(401, {'error': 'Console verrouillée : saisissez le code PIN.'})
            try:
                return self._send(200, self.dispatch(route, payload))
            except (OdooError, ValueError, KeyError) as error:
                return self._send(400, {'error': str(error)})
            except Exception as error:
                _logger.exception('Console : erreur sur %s', route)
                return self._send(500, {'error': str(error)})

        def dispatch(self, route, payload):
            if route == '/api/server/check':
                result = check_server(payload.get('address'))
                return dict(result, ok=True)
            if route == '/api/pair':
                return self.pair(payload)
            if route == '/api/device/save':
                return self.save_device(payload)
            if route == '/api/device/remove':
                config.remove_device(payload['id'])
                engine.reload()
                _logger.info('Pointeuse retirée de la passerelle.')
                return {'ok': True}
            if route == '/api/device/test':
                info = Device(payload['ip'], payload.get('port') or 4370, payload.get('comm_key') or 0,
                              payload.get('timeout') or 10).probe()
                return {'ok': True, 'info': info}
            if route == '/api/scan':
                return dict(scan_devices(int(payload.get('port') or 4370)), ok=True)
            if route == '/api/pin':
                config.set_pin(payload.get('pin') or '')
                sessions.clear()
                _logger.info('Code PIN de la console %s.', 'défini' if payload.get('pin') else 'supprimé')
                return {'ok': True}
            raise KeyError('route inconnue %s' % route)

        def pair(self, payload):
            url = payload['url'].rstrip('/')
            database = (payload.get('database') or '').strip()
            client = OdooClient(url, database)
            ping = client.call('ping', {})
            if not ping.get('module_version'):
                raise OdooError("Le module « Gestion des pointages » n'est pas installé sur la base %s."
                                % (ping.get('database') or database))
            result = client.call('pair', {'code': payload.get('code'), 'agent': agent_info()})
            if not result.get('ok'):
                raise OdooError(result.get('error') or 'Association refusée.')
            remote = result['device']
            values = {
                'id': uuid.uuid4().hex,
                'name': remote.get('name') or 'Pointeuse',
                'server_url': url,
                'database': result.get('database') or database,
                'company': result.get('company'),
                'token': result['token'],
                'ip': remote.get('ip'),
                'port': remote.get('port') or 4370,
                'comm_key': remote.get('comm_key') or 0,
                'timeout': remote.get('timeout') or 10,
                'enabled': True,
            }
            config.upsert_device(values)
            engine.reload()
            _logger.info('Pointeuse « %s » associée à %s (%s).', values['name'], url, values['database'])
            return {'ok': True, 'device': {key: value for key, value in values.items() if key != 'token'}}

        def save_device(self, payload):
            current = config.get_device(payload['id'])
            if not current:
                raise KeyError('pointeuse inconnue')
            for key in ('name', 'ip'):
                if key in payload:
                    current[key] = str(payload[key]).strip()
            for key in ('port', 'comm_key', 'timeout'):
                if key in payload:
                    current[key] = int(payload[key])
            if 'enabled' in payload:
                current['enabled'] = bool(payload['enabled'])
            ipaddress.ip_address(current['ip'])  # validates the address
            config.upsert_device(current)
            engine.reload()
            _logger.info('Paramètres de la pointeuse « %s » enregistrés.', current['name'])
            return {'ok': True}

    return Handler


def start_console(config, engine, port=UI_PORT):
    server = ConsoleServer(('127.0.0.1', port), make_handler(config, engine))
    threading.Thread(target=server.serve_forever, name='console', daemon=True).start()
    return server


# ---------------------------------------------------------------------------
# Console page (single page, no external resource: works without Internet)
# ---------------------------------------------------------------------------
CONSOLE_HTML = r'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Passerelle Pointeuse PrimeTech</title>
<style>
:root{--brand:#5b3fd1;--brand-2:#7d63ec;--ok:#16a34a;--warn:#d97706;--err:#dc2626;--muted:#6b7280;
--bg:#f4f5fb;--card:#fff;--line:#e5e7eb;--text:#111827;--radius:14px}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{background:linear-gradient(120deg,var(--brand),var(--brand-2));color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header .logo{width:42px;height:42px;border-radius:12px;background:rgba(255,255,255,.18);display:grid;place-items:center;font-size:22px}
header h1{font-size:19px;margin:0}header small{opacity:.85}
header .spacer{flex:1}
.pill{display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:99px;font-size:13px;font-weight:600;background:rgba(255,255,255,.18)}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;background:#9ca3af}
.dot.ok{background:var(--ok);box-shadow:0 0 0 0 rgba(22,163,74,.6);animation:pulse 2s infinite}
.dot.warning{background:var(--warn)}.dot.error{background:var(--err);animation:pulse-err 1.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(22,163,74,.55)}70%{box-shadow:0 0 0 8px rgba(22,163,74,0)}100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}}
@keyframes pulse-err{0%{box-shadow:0 0 0 0 rgba(220,38,38,.55)}70%{box-shadow:0 0 0 8px rgba(220,38,38,0)}100%{box-shadow:0 0 0 0 rgba(220,38,38,0)}}
main{max-width:1180px;margin:0 auto;padding:24px}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:18px;flex-wrap:wrap}
.toolbar h2{margin:0;font-size:18px;flex:1}
button,.btn{font:inherit;border:1px solid var(--line);background:#fff;border-radius:10px;padding:8px 14px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:.15s}
button:hover{border-color:var(--brand);color:var(--brand)}button:disabled{opacity:.5;cursor:default}
button.primary{background:var(--brand);color:#fff;border-color:var(--brand)}button.primary:hover{background:var(--brand-2);color:#fff}
button.danger:hover{border-color:var(--err);color:var(--err)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:18px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.card.enter{animation:enter .35s ease both}
@keyframes enter{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.card h3{margin:0;font-size:16px;display:flex;align-items:center;gap:8px}
.card .sub{color:var(--muted);font-size:13px;margin-top:2px}
.status{margin:14px 0;padding:10px 12px;border-radius:10px;font-size:14px;background:#f3f4f6}
.status.ok{background:#ecfdf3;color:#166534}.status.warning{background:#fffbeb;color:#92400e}.status.error{background:#fef2f2;color:#991b1b}
.kv{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}
.kv div{background:#f9fafb;border-radius:10px;padding:8px 10px}.kv b{display:block;font-size:18px}.kv span{font-size:12px;color:var(--muted)}
.meta{font-size:13px;color:var(--muted);line-height:1.7}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.empty{text-align:center;padding:50px 20px;color:var(--muted)}.empty .big{font-size:46px}
.logs{background:#0f172a;color:#cbd5e1;border-radius:var(--radius);padding:14px;font:12.5px/1.6 Consolas,monospace;max-height:260px;overflow:auto;margin-top:22px}
.logs .ERROR{color:#fca5a5}.logs .WARNING{color:#fcd34d}
.modal-back{position:fixed;inset:0;background:rgba(17,24,39,.5);display:none;align-items:center;justify-content:center;padding:16px;z-index:10}
.modal-back.open{display:flex}
.modal{background:#fff;border-radius:18px;width:min(640px,100%);max-height:92vh;overflow:auto;padding:24px;animation:enter .25s ease both}
.modal h2{margin:0 0 4px;font-size:19px}.modal p.help{color:var(--muted);font-size:14px;margin:4px 0 16px}
.steps{display:flex;gap:6px;margin:12px 0 20px}.steps div{flex:1;height:5px;border-radius:9px;background:var(--line)}.steps div.on{background:var(--brand)}
label{display:block;font-size:13px;font-weight:600;margin:12px 0 5px}
input,select{width:100%;font:inherit;padding:10px 12px;border:1px solid #d1d5db;border-radius:10px;background:#fff}
input:focus,select:focus{outline:2px solid #c4b5fd;border-color:var(--brand)}
.row{display:flex;gap:10px}.row>*{flex:1}
.code{font:600 22px Consolas,monospace;letter-spacing:3px;text-transform:uppercase;text-align:center}
.note{font-size:13px;border-radius:10px;padding:10px 12px;margin-top:12px}
.note.ok{background:#ecfdf3;color:#166534}.note.err{background:#fef2f2;color:#991b1b}.note.info{background:#eef2ff;color:#3730a3}
.footer{display:flex;justify-content:space-between;gap:10px;margin-top:22px}
.found{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-top:8px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.spin{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.lock{max-width:380px;margin:80px auto;text-align:center}
</style>
</head>
<body>
<header>
  <div class="logo">⏱</div>
  <div><h1>Passerelle Pointeuse PrimeTech</h1><small id="host">…</small></div>
  <div class="spacer"></div>
  <span class="pill" id="global"><span class="dot"></span><span>Chargement…</span></span>
</header>
<main id="app"></main>

<div class="modal-back" id="modal"><div class="modal" id="modal-body"></div></div>

<script>
const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null;
let wizard = null;
const shown = new Set();  // cards already animated (the page refreshes every 3 s)

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-PrimeTech-Relay': '1'},
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || ('Erreur ' + response.status));
  return data;
}

const STATE_LABEL = {ok: 'Synchronisée', warning: 'Synchronisée (à vérifier)', error: 'Erreur', pending: 'En attente', paused: 'Suspendue'};

function deviceCard(item, index) {
  const c = item.config, s = item.status, info = s.info || {};
  const memory = info.records_cap ? Math.round(100 * (info.records || 0) / info.records_cap) : null;
  const fresh = !shown.has(c.id); shown.add(c.id);
  return `<div class="card${fresh ? ' enter' : ''}" style="animation-delay:${index * 60}ms">
    <h3><span class="dot ${esc(s.state)}"></span>${esc(c.name)}</h3>
    <div class="sub">${esc(info.device_name || 'ZKTeco')} ${info.serial ? '· n° ' + esc(info.serial) : ''} · ${esc(c.ip)}:${esc(c.port)}</div>
    <div class="status ${esc(s.state)}"><b>${esc(STATE_LABEL[s.state] || s.state)}</b> — ${esc(s.message)}</div>
    <div class="kv">
      <div><b>${s.created_today ?? 0}</b><span>nouveaux aujourd'hui</span></div>
      <div><b>${s.records_in_memory ?? '—'}</b><span>en mémoire${memory !== null ? ' (' + memory + ' %)' : ''}</span></div>
      <div><b>${info.users ?? '—'}</b><span>utilisateurs</span></div>
    </div>
    <div class="meta">
      Odoo : <b>${esc(c.server_url)}</b> · base ${esc(c.database || '—')}${c.company ? ' · ' + esc(c.company) : ''}<br>
      Dernière synchro : ${esc(s.last_sync || 'jamais')}${s.latency_ms ? ' · ' + s.latency_ms + ' ms' : ''}<br>
      Prochaine : ${c.enabled === false ? 'suspendue' : (s.next_sync_in ? 'dans ' + s.next_sync_in + ' s' : 'imminente')} · toutes les ${s.interval} s
    </div>
    <div class="actions">
      <button class="primary" onclick="syncNow('${c.id}')">⟳ Synchroniser</button>
      <button onclick="editDevice('${c.id}')">⚙ Paramètres</button>
      <button onclick="toggleDevice('${c.id}', ${c.enabled === false})">${c.enabled === false ? '▶ Reprendre' : '⏸ Suspendre'}</button>
      <button class="danger" onclick="removeDevice('${c.id}')">✕ Retirer</button>
    </div>
  </div>`;
}

function render() {
  if (!state) return;
  $('#host').textContent = `PC ${state.host} · version ${state.version} · démarrée le ${state.started_at}`;
  const states = state.devices.map((d) => d.status.state);
  const globalState = !states.length ? '' : states.includes('error') ? 'error' : states.includes('warning') ? 'warning' : 'ok';
  const label = !states.length ? 'Aucune pointeuse' : globalState === 'error' ? 'Attention requise' : 'Opérationnelle';
  $('#global').innerHTML = `<span class="dot ${globalState}"></span><span>${label}</span>`;
  if (!state.unlocked) {
    $('#app').innerHTML = `<div class="card lock"><div style="font-size:40px">🔒</div><h3 style="justify-content:center">Console verrouillée</h3>
      <p class="help">Saisissez le code PIN administrateur pour modifier la passerelle. La synchronisation continue en arrière-plan.</p>
      <input type="password" id="pin" placeholder="Code PIN" onkeydown="if(event.key==='Enter')unlock()">
      <div class="actions" style="justify-content:center"><button class="primary" onclick="unlock()">Déverrouiller</button></div>
      <div id="pin-note"></div></div>`;
    return;
  }
  const devices = state.devices.length
    ? `<div class="grid">${state.devices.map(deviceCard).join('')}</div>`
    : `<div class="card empty"><div class="big">🔗</div><h3 style="justify-content:center">Aucune pointeuse associée</h3>
       <p>Associez cette passerelle à votre serveur Odoo pour envoyer les pointages automatiquement.</p>
       <button class="primary" onclick="openWizard()">＋ Ajouter une pointeuse</button></div>`;
  const logs = state.logs.slice().reverse().map((l) => `<div class="${esc(l.level)}">${esc(l.time)}  ${esc(l.message)}</div>`).join('');
  $('#app').innerHTML = `
    <div class="toolbar"><h2>Pointeuses</h2>
      <button onclick="syncNow()">⟳ Tout synchroniser</button>
      <button onclick="openPin()">🔒 ${state.has_pin ? 'Changer le PIN' : 'Protéger par PIN'}</button>
      <button class="primary" onclick="openWizard()">＋ Ajouter une pointeuse</button></div>
    ${devices}
    <div class="logs">${logs || 'Journal vide.'}</div>`;
}

async function refresh() {
  try { state = await api('/api/state'); if (!$('#modal').classList.contains('open')) render(); }
  catch (error) { $('#global').innerHTML = '<span class="dot error"></span><span>Service arrêté</span>'; }
}

async function unlock() {
  try { await api('/api/unlock', {pin: $('#pin').value}); await refresh(); }
  catch (error) { $('#pin-note').innerHTML = `<div class="note err">${esc(error.message)}</div>`; }
}
async function syncNow(id) { await api('/api/sync', {id}); setTimeout(refresh, 1500); }
async function removeDevice(id) {
  if (!confirm('Retirer cette pointeuse de la passerelle ? Elle ne sera plus synchronisée depuis ce PC.')) return;
  await api('/api/device/remove', {id}); refresh();
}
async function toggleDevice(id, enabled) { await api('/api/device/save', {id, enabled}); refresh(); }

// ---------------------------------------------------------------- modal helpers
function openModal(html) { $('#modal-body').innerHTML = html; $('#modal').classList.add('open'); }
function closeModal() { $('#modal').classList.remove('open'); wizard = null; refresh(); }
function note(id, kind, text) { $(id).innerHTML = text ? `<div class="note ${kind}">${text}</div>` : ''; }
function busy(button, on, text) { button.disabled = on; if (on) { button.dataset.label = button.innerHTML; button.innerHTML = `<span class="spin"></span> ${text}`; } else if (button.dataset.label) { button.innerHTML = button.dataset.label; } }

function openPin() {
  openModal(`<h2>Code PIN administrateur</h2>
    <p class="help">Le PIN protège les réglages de la passerelle (ajout, modification, suppression). Laissez vide pour retirer la protection.</p>
    <label>Nouveau code PIN</label><input type="password" id="new-pin" maxlength="12" placeholder="4 à 12 chiffres">
    <div id="pin-msg"></div>
    <div class="footer"><button onclick="closeModal()">Annuler</button><button class="primary" onclick="savePin()">Enregistrer</button></div>`);
}
async function savePin() {
  const pin = $('#new-pin').value.trim();
  if (pin && !/^\d{4,12}$/.test(pin)) return note('#pin-msg', 'err', 'Le PIN doit contenir 4 à 12 chiffres.');
  try { await api('/api/pin', {pin}); closeModal(); } catch (error) { note('#pin-msg', 'err', esc(error.message)); }
}

// ---------------------------------------------------------------- wizard: add a device
function steps(n) { return `<div class="steps">${[1,2,3].map((i) => `<div class="${i <= n ? 'on' : ''}"></div>`).join('')}</div>`; }

function openWizard() {
  wizard = {step: 1};
  openModal(`<h2>Ajouter une pointeuse</h2>${steps(1)}
    <p class="help"><b>Étape 1 — Serveur Odoo.</b> Saisissez le nom de domaine du serveur (ex. <i>hitech.primetechafrik.com</i>) ou son adresse IP et son port (ex. <i>38.247.147.212:18077</i>).</p>
    <label>Adresse du serveur Odoo</label>
    <input id="address" placeholder="hitech.primetechafrik.com" onkeydown="if(event.key==='Enter')checkServer(this)">
    <div id="server-note"></div>
    <div id="db-zone"></div>
    <div class="footer"><button onclick="closeModal()">Annuler</button><button class="primary" id="btn-check" onclick="checkServer(this)">Vérifier le serveur →</button></div>`);
  setTimeout(() => $('#address').focus(), 50);
}

async function checkServer(button) {
  button = $('#btn-check');
  const address = $('#address').value.trim();
  if (!address) return note('#server-note', 'err', 'Saisissez une adresse.');
  busy(button, true, 'Recherche du serveur…'); note('#server-note');
  try {
    const result = await api('/api/server/check', {address});
    wizard.url = result.url;
    const dbs = result.databases;
    note('#server-note', 'ok', `✓ Serveur Odoo ${esc(result.version || '')} trouvé : <b>${esc(result.url)}</b>`);
    $('#db-zone').innerHTML = (dbs && dbs.length)
      ? `<label>Base de données</label><select id="database">${dbs.map((d) => `<option>${esc(d)}</option>`).join('')}</select>`
      : `<label>Base de données</label><input id="database" placeholder="ex. HITECH_PROD"><div class="note info">La liste des bases n'est pas publiée par ce serveur : saisissez le nom de la base.</div>`;
    button.outerHTML = `<button class="primary" id="btn-next" onclick="toPairing()">Continuer →</button>`;
  } catch (error) {
    note('#server-note', 'err', esc(error.message));
  } finally { if (document.body.contains(button)) busy(button, false); }
}

function toPairing() {
  wizard.database = ($('#database').value || '').trim();
  if (!wizard.database) return note('#server-note', 'err', 'Indiquez la base de données.');
  wizard.step = 2;
  openModal(`<h2>Ajouter une pointeuse</h2>${steps(2)}
    <p class="help"><b>Étape 2 — Code d'association.</b> Dans Odoo : <i>Gestion des pointages › Pointeuses</i>, ouvrez la pointeuse, onglet <i>Passerelle</i>, puis cliquez sur <b>Générer un code d'association</b>.</p>
    <div class="meta">Serveur : <b>${esc(wizard.url)}</b> · base <b>${esc(wizard.database)}</b></div>
    <label>Code d'association</label>
    <input id="code" class="code" maxlength="9" placeholder="XXXX-XXXX" onkeydown="if(event.key==='Enter')pair()">
    <div id="pair-note"></div>
    <div class="footer"><button onclick="openWizard()">← Retour</button><button class="primary" id="btn-pair" onclick="pair()">Associer →</button></div>`);
  setTimeout(() => $('#code').focus(), 50);
}

async function pair() {
  const button = $('#btn-pair');
  busy(button, true, 'Association…'); note('#pair-note');
  try {
    const result = await api('/api/pair', {url: wizard.url, database: wizard.database, code: $('#code').value});
    wizard.device = result.device;
    toDevice();
  } catch (error) { note('#pair-note', 'err', esc(error.message)); busy(button, false); }
}

function toDevice() {
  const d = wizard.device;
  wizard.step = 3;
  openModal(`<h2>Ajouter une pointeuse</h2>${steps(3)}
    <div class="note ok">✓ Passerelle associée à la pointeuse « <b>${esc(d.name)}</b> » ${d.company ? '(' + esc(d.company) + ')' : ''}.</div>
    <p class="help"><b>Étape 3 — Pointeuse sur le réseau local.</b> Vérifiez l'adresse de la pointeuse ou recherchez-la automatiquement.</p>
    ${deviceFields(d)}
    <div class="footer"><button onclick="scan()" id="btn-scan">🔍 Rechercher sur le réseau</button>
      <span><button onclick="testDevice()" id="btn-test">Tester</button> <button class="primary" onclick="finishDevice()">Terminer ✓</button></span></div>`);
}

function deviceFields(d) {
  return `<input type="hidden" id="dev-id" value="${esc(d.id)}">
    <label>Nom</label><input id="dev-name" value="${esc(d.name)}">
    <div class="row"><div><label>Adresse IP de la pointeuse</label><input id="dev-ip" value="${esc(d.ip)}"></div>
      <div><label>Port</label><input id="dev-port" type="number" value="${esc(d.port || 4370)}"></div>
      <div><label>Clé de communication</label><input id="dev-key" type="number" value="${esc(d.comm_key || 0)}"></div></div>
    <div id="dev-note"></div><div id="scan-zone"></div>`;
}

function deviceValues() {
  return {id: $('#dev-id').value, name: $('#dev-name').value, ip: $('#dev-ip').value.trim(),
          port: Number($('#dev-port').value || 4370), comm_key: Number($('#dev-key').value || 0)};
}

async function testDevice() {
  const button = $('#btn-test'); busy(button, true, 'Test…'); note('#dev-note');
  try {
    const result = await api('/api/device/test', deviceValues());
    const i = result.info;
    note('#dev-note', 'ok', `✓ Pointeuse joignable : <b>${esc(i.device_name || 'ZKTeco')}</b> n° ${esc(i.serial || '?')} · ${i.users ?? '?'} utilisateur(s) · ${i.records ?? '?'} pointage(s) en mémoire.`);
  } catch (error) { note('#dev-note', 'err', 'Pointeuse injoignable : ' + esc(error.message)); }
  busy(button, false);
}

async function scan() {
  const button = $('#btn-scan'); busy(button, true, 'Recherche (≈ 10 s)…'); $('#scan-zone').innerHTML = '';
  try {
    const result = await api('/api/scan', {port: Number($('#dev-port').value || 4370)});
    $('#scan-zone').innerHTML = result.devices.length
      ? result.devices.map((d) => `<div class="found"><span><b>${esc(d.model || 'Appareil')}</b> ${d.serial ? 'n° ' + esc(d.serial) : ''}<br><small>${esc(d.ip)}:${esc(d.port)} ${d.note ? '· ' + esc(d.note) : ''}</small></span>
          <button onclick="$('#dev-ip').value='${esc(d.ip)}';$('#dev-port').value='${esc(d.port)}'">Utiliser</button></div>`).join('')
      : `<div class="note err">Aucune pointeuse trouvée sur ${esc(result.networks.join(', ') || 'le réseau')}. Vérifiez qu'elle est allumée et branchée au même réseau.</div>`;
  } catch (error) { $('#scan-zone').innerHTML = `<div class="note err">${esc(error.message)}</div>`; }
  busy(button, false);
}

async function finishDevice() {
  try { await api('/api/device/save', deviceValues()); await api('/api/sync', {id: $('#dev-id').value}); closeModal(); }
  catch (error) { note('#dev-note', 'err', esc(error.message)); }
}

function editDevice(id) {
  const item = state.devices.find((d) => d.config.id === id);
  openModal(`<h2>Paramètres de la pointeuse</h2>
    <p class="help">Associée à <b>${esc(item.config.server_url)}</b> (base ${esc(item.config.database)}). Pour changer de serveur, retirez la pointeuse puis associez-la à nouveau.</p>
    ${deviceFields(item.config)}
    <div class="footer"><button onclick="scan()" id="btn-scan">🔍 Rechercher sur le réseau</button>
      <span><button onclick="closeModal()">Annuler</button> <button onclick="testDevice()" id="btn-test">Tester</button> <button class="primary" onclick="finishDevice()">Enregistrer</button></span></div>`);
}

$('#modal').addEventListener('click', (event) => { if (event.target.id === 'modal' && wizard === null) closeModal(); });
refresh().then(() => {
  // console.html#ajouter opens the "add a device" wizard directly (link from the installer).
  if (location.hash === '#ajouter' && state && state.unlocked) openWizard();
});
setInterval(refresh, 3000);
</script>
</body>
</html>
'''


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def run_service(open_browser, port=UI_PORT):
    url = 'http://localhost:%s' % port
    config = Config()
    engine = Engine(config)
    try:
        start_console(config, engine, port)
    except OSError:
        _logger.info('La passerelle tourne déjà sur ce PC : ouverture de la console.')
        if open_browser:
            webbrowser.open(url)
        return
    _logger.info('Passerelle PrimeTech %s démarrée sur %s (%s pointeuse(s)). Console : %s',
                 VERSION, socket.gethostname(), len(config.devices()), url)
    if open_browser:
        webbrowser.open(url)
    engine.run_forever()


def run_test():
    config = Config()
    if not config.devices():
        _logger.warning('Aucune pointeuse configurée : ouvrez la console %s pour en ajouter une.', CONSOLE_URL)
        return True
    ok = True
    for values in config.devices():
        name = values.get('name')
        try:
            info = Device(values['ip'], values.get('port', 4370), values.get('comm_key', 0),
                          values.get('timeout', 10)).probe()
            _logger.info('[%s] Pointeuse OK : %s (%s), %s pointage(s) en mémoire.', name,
                         info.get('device_name'), info.get('serial'), info.get('records'))
        except Exception as error:
            ok = False
            _logger.error('[%s] Pointeuse injoignable (%s:%s) : %s', name, values['ip'], values.get('port'), error)
        try:
            hello = OdooClient(values['server_url'], values.get('database'), values['token']).call(
                'hello', {'agent': agent_info()})
            _logger.info('[%s] Odoo OK : « %s », synchronisation toutes les %s s.', name,
                         hello.get('device'), hello.get('interval'))
        except Exception as error:
            ok = False
            _logger.error('[%s] Odoo injoignable (%s) : %s', name, values['server_url'], error)
    return ok


def main():
    parser = argparse.ArgumentParser(description='Passerelle de pointeuses PrimeTech')
    parser.add_argument('--once', action='store_true', help='une synchronisation de chaque pointeuse')
    parser.add_argument('--test', action='store_true', help='tester les pointeuses et Odoo')
    parser.add_argument('--service', action='store_true', help='mode tâche de fond (sans navigateur)')
    parser.add_argument('--port', type=int, default=UI_PORT, help='port de la console (défaut %s)' % UI_PORT)
    args = parser.parse_args()
    setup_logging()
    if args.test:
        sys.exit(0 if run_test() else 1)
    if args.once:
        config = Config()
        for values in config.devices():
            DeviceWorker(values).run_if_due(force=True)
        return
    # Double-click: start (or join) the gateway and open its console.
    run_service(open_browser=not args.service, port=args.port)


if __name__ == '__main__':
    main()
