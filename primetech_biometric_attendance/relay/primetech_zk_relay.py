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
import traceback
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

VERSION = '2.5.1'
UI_PORT = 47321
SESSION_TTL_SECONDS = 30 * 60
BATCH_SIZE = 2000
POLL_SECONDS = 10  # how often Odoo is asked whether a request is waiting
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
        time_label = datetime.fromtimestamp(record.created).strftime('%d/%m %H:%M:%S')
        message = record.getMessage()
        last = self.records[-1] if self.records else None
        if last and last['message'] == message and last['level'] == record.levelname:
            last['repeat'] = last.get('repeat', 1) + 1
            last['last_time'] = time_label
            return
        self.records.append({'time': time_label, 'level': record.levelname, 'message': message})


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
        """Store a normalized console PIN.

        The web console submits text, but normalising here as well keeps the
        value that is hashed and the value checked at unlock strictly aligned.
        """
        pin = str(pin or '').strip()
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
        try:
            salt, digest = stored.split('$', 1)
            return secrets.compare_digest(self._hash(str(pin or '').strip(), salt), digest)
        except (TypeError, ValueError):
            # A malformed value must never make the unlock endpoint fail open
            # or return a server error to the person entering their PIN.
            _logger.error('Le code PIN enregistré est invalide.')
            return False


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
class DeviceBusy(Exception):
    """The device refused a write: the command can be retried later."""


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

    def list_users(self):
        conn = self.connect()
        try:
            users = conn.get_users() or []
            info = self.info(conn)
        finally:
            conn.disconnect()
        return [{'uid': user.uid, 'user_id': str(user.user_id), 'name': user.name,
                 'privilege': user.privilege, 'card': user.card, 'has_password': bool(user.password)}
                for user in users], info

    def list_punches(self):
        """All the punches stored in the device, most recent first."""
        conn = self.connect()
        try:
            conn.disable_device()
            try:
                users = conn.get_users() or []
                records = conn.get_attendance() or []
            finally:
                conn.enable_device()
        finally:
            conn.disconnect()
        names = {str(user.user_id): user.name for user in users}
        punches = [{'user_id': str(record.user_id), 'name': names.get(str(record.user_id), ''),
                    'time': record.timestamp.strftime(TIME_FORMAT), 'status': record.status,
                    'punch': record.punch} for record in records if record.timestamp]
        punches.sort(key=lambda punch: punch['time'], reverse=True)
        return punches

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

    def user_command(self, command):
        """Create/update or remove one user.

        This firmware sometimes refuses writes for a few seconds ("Can't set
        user"), typically on a session opened right after another one: open a
        fresh session and try again.  If the device stays busy the error is
        flagged ``retry`` so that Odoo queues the command again.
        """
        name, user_id = command.get('name'), str(command['user_id'])
        last_error = None
        for attempt in range(3):
            if attempt:
                time.sleep(3 * attempt)
            conn = self.connect()
            try:
                # get_users() also prepares the next free UID used by set_user().
                existing = next((user for user in conn.get_users() if str(user.user_id) == user_id), None)
                if name == 'remove_user':
                    if existing:
                        conn.delete_user(uid=existing.uid, user_id=user_id)
                    return {'message': 'Utilisateur %s retiré de la pointeuse.' % user_id}
                conn.set_user(uid=existing.uid if existing else None, name=command.get('user_name') or '',
                              privilege=int(command.get('privilege') or 0),
                              password=command.get('password') or '', group_id='', user_id=user_id,
                              card=int(command.get('card') or 0))
                assigned = next((user for user in conn.get_users() if str(user.user_id) == user_id), None)
                return {'message': 'Utilisateur %s « %s » %s sur la pointeuse.' % (
                            user_id, command.get('user_name'), 'mis à jour' if existing else 'créé'),
                        'uid': assigned.uid if assigned else None}
            except Exception as error:
                last_error = error
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass
        raise DeviceBusy(str(last_error))

    def run_command(self, command):
        name = command.get('name')
        if name in ('push_user', 'remove_user'):
            return self.user_command(command)
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
class DeviceJournal:
    """Persistent, exhaustive journal of one device (JSON lines, rotating files)."""

    MAX_BYTES = 2 * 1024 * 1024
    BACKUPS = 5
    LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')

    def __init__(self, device_id, name):
        self.directory = os.path.join(base_dir(), 'logs')
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, '%s.jsonl' % device_id)
        self.name = name
        self.lock = threading.Lock()
        self.last = None  # (key, entry, offset of its line) to merge identical consecutive events

    def write(self, level, category, message, **details):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        key = (level, category, message)
        with self.lock:
            if self.last and self.last[0] == key and os.path.exists(self.path) \
                    and os.path.getsize(self.path) >= self.last[2]:
                # Same event again: update the existing line (counter + last occurrence).
                entry, offset = self.last[1], self.last[2]
                entry['repeat'] = entry.get('repeat', 1) + 1
                entry['last_time'] = now
                if details:
                    entry['details'] = details
                with open(self.path, 'r+b') as handle:
                    handle.seek(offset)
                    handle.truncate()
                    handle.write((json.dumps(entry, ensure_ascii=False, default=str) + '\n').encode('utf-8'))
            else:
                entry = {'time': now, 'level': level, 'category': category, 'message': message}
                if details:
                    entry['details'] = details
                if os.path.exists(self.path) and os.path.getsize(self.path) > self.MAX_BYTES:
                    self._rotate()
                offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0
                with open(self.path, 'ab') as handle:
                    handle.write((json.dumps(entry, ensure_ascii=False, default=str) + '\n').encode('utf-8'))
                self.last = (key, entry, offset)
        # The main page log merges consecutive repeats on its side.
        if level != 'DEBUG':
            _logger.log(getattr(logging, level), '[%s] %s', self.name, message)

    def _rotate(self):
        for index in range(self.BACKUPS - 1, 0, -1):
            source = '%s.%s' % (self.path, index)
            if os.path.exists(source):
                os.replace(source, '%s.%s' % (self.path, index + 1))
        os.replace(self.path, self.path + '.1')

    def debug(self, category, message, **details):
        self.write('DEBUG', category, message, **details)

    def info(self, category, message, **details):
        self.write('INFO', category, message, **details)

    def warning(self, category, message, **details):
        self.write('WARNING', category, message, **details)

    def error(self, category, message, **details):
        self.write('ERROR', category, message, **details)

    def read(self, level='', category='', day='', query='', offset=0, limit=200):
        """Entries matching the filters, most recent first, plus statistics."""
        files = [self.path] + ['%s.%s' % (self.path, index) for index in range(1, self.BACKUPS + 1)]
        minimum = self.LEVELS.index(level) if level in self.LEVELS else 0
        query = (query or '').lower()
        entries, stats = [], {'total': 0, 'errors_24h': 0, 'warnings_24h': 0, 'last_error': None,
                              'oldest': None, 'categories': {}}
        since = (datetime.now().timestamp() - 86400)
        with self.lock:
            for path in files:
                if not os.path.exists(path):
                    continue
                with open(path, encoding='utf-8', errors='replace') as handle:
                    lines = handle.readlines()
                for line in reversed(lines):
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    stats['total'] += 1
                    stats['oldest'] = entry['time']
                    stats['categories'][entry['category']] = stats['categories'].get(entry['category'], 0) + 1
                    try:
                        recent = datetime.strptime(entry['time'][:19], TIME_FORMAT).timestamp() >= since
                    except ValueError:
                        recent = False
                    if entry['level'] == 'ERROR':
                        stats['last_error'] = stats['last_error'] or entry
                        stats['errors_24h'] += entry.get('repeat', 1) if recent else 0
                    elif entry['level'] == 'WARNING':
                        stats['warnings_24h'] += entry.get('repeat', 1) if recent else 0
                    if self.LEVELS.index(entry.get('level', 'INFO')) < minimum:
                        continue
                    if category and entry['category'] != category:
                        continue
                    if day and not entry['time'].startswith(day):
                        continue
                    if query and query not in json.dumps(entry, ensure_ascii=False).lower():
                        continue
                    entries.append(entry)
        return {'entries': entries[offset:offset + limit], 'matching': len(entries), 'stats': stats}


class DeviceWorker:
    """Synchronisation state of one configured device."""

    def __init__(self, config_values):
        self.lock = threading.Lock()  # one session at a time: synchronisation or console
        self.config = config_values
        self.journal = DeviceJournal(config_values['id'], config_values.get('name'))
        self.journal.info('service', 'Passerelle %s démarrée sur %s : pointeuse %s:%s, serveur %s (base %s).' % (
            VERSION, socket.gethostname(), config_values.get('ip'), config_values.get('port'),
            config_values.get('server_url'), config_values.get('database')))
        self.client = None
        self.interval = 60
        self.next_run = 0.0
        self.last_poll = 0.0
        self.command_results = []
        self.status = {
            'state': 'pending', 'message': 'En attente de la première synchronisation.',
            'last_sync': None, 'last_success': None, 'odoo_device': None,
            'info': {}, 'records_in_memory': None, 'sent_today': 0, 'created_today': 0,
            'today': datetime.now().date().isoformat(), 'latency_ms': None, 'unknown': [],
        }

    def update_config(self, values):
        changes = {key: [self.config.get(key), values.get(key)] for key in
                   ('name', 'ip', 'port', 'comm_key', 'timeout', 'enabled', 'server_url', 'database')
                   if self.config.get(key) != values.get(key)}
        if changes:
            self.journal.name = values.get('name')
            self.journal.info('config', 'Paramètres modifiés : %s.' % ', '.join(changes), changes=changes)
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
        journal = self.journal
        started = time.monotonic()
        today = datetime.now().date().isoformat()
        if self.status['today'] != today:
            self.status.update(today=today, sent_today=0, created_today=0)
        self.status['last_sync'] = now_str()
        steps = self.steps = []  # detailed steps, attached to the single journal line of this cycle

        step = time.monotonic()
        hello = self.odoo().call('hello', {'agent': agent_info()})
        if not hello.get('ok'):
            raise OdooError(hello.get('error') or 'Réponse invalide.')
        self.status['odoo_device'] = hello.get('device')
        self.interval = hello.get('interval') or self.interval
        steps.append('Odoo joint en %.1f s : pointeuse « %s », pointages demandés depuis %s, intervalle %s s.' % (
            time.monotonic() - step, hello.get('device'), hello.get('since') or 'le début de la mémoire',
            self.interval))

        step = time.monotonic()
        users, records, info = self.device().read(hello.get('since'))
        self.status['info'] = info
        self.status['records_in_memory'] = info.get('records')
        steps.append('Pointeuse lue en %.1f s : %s utilisateur(s), %s/%s pointage(s) en mémoire, %s à envoyer, '
                     'heure de la pointeuse %s.' % (time.monotonic() - step, len(users), info.get('records'),
                                                    info.get('records_cap'), len(records), info.get('device_time')))

        batches = [records[index:index + BATCH_SIZE]
                   for index in range(0, len(records), BATCH_SIZE)] or [[]]
        created, response = 0, {}
        for number, batch in enumerate(batches, 1):
            response = self.odoo().call('push', {
                'agent': agent_info(), 'users': users, 'info': info, 'records': batch,
                'command_results': self.command_results,
            })
            if not response.get('ok'):
                raise OdooError(response.get('error') or 'Réponse invalide.')
            self.command_results = []
            created += response.get('created') or 0
            steps.append('Lot %s/%s envoyé à Odoo en %s ms : %s pointage(s), %s nouveau(x), %s commande(s) reçue(s).' % (
                number, len(batches), response.get('_latency_ms'), len(batch), response.get('created') or 0,
                len(response.get('commands') or [])))
        self.interval = response.get('interval') or self.interval
        self.status.update(latency_ms=response.get('_latency_ms'), unknown=response.get('unknown') or [],
                           mapping=response.get('mapping') or {})
        self.status['sent_today'] += len(records)
        self.status['created_today'] += created
        steps.append('Durée totale : %.1f s.' % (time.monotonic() - started))
        if response.get('unknown'):
            journal.warning('sync', 'Synchronisation : %s nouveau(x) pointage(s) ; identifiants sans employé dans '
                            'Odoo : %s.' % (created, ', '.join(response['unknown'])), steps=steps)
        elif created:
            journal.info('sync', 'Synchronisation : %s nouveau(x) pointage(s) envoyé(s) à Odoo.' % created, steps=steps)
        else:
            journal.debug('sync', 'Synchronisation réussie, aucun nouveau pointage.', steps=steps)

        # Commands run after a successful push, so clearing the memory never loses a punch.
        for command in response.get('commands') or []:
            result = {'command': command.get('name'), 'ref': command.get('ref')}
            shown = {key: value for key, value in command.items() if key != 'password'}
            try:
                outcome = self.device().run_command(command)
                if isinstance(outcome, dict):
                    result.update(outcome)
                else:
                    result['message'] = outcome
                result['ok'] = True
                self.command_results.append(result)
                journal.info('command', 'Commande %s : %s' % (command.get('name'), result['message']), command=shown)
            except Exception as error:
                result.update(ok=False, message=str(error))
                if isinstance(error, DeviceBusy):
                    # Odoo puts the command back in the queue for the next synchronisation.
                    result.update(retry=True, retry_command=command)
                    journal.warning('command', 'Commande %s : pointeuse occupée, nouvel essai à la prochaine '
                                    'synchronisation.' % command.get('name'), command=shown, error=str(error))
                else:
                    journal.error('command', 'Commande %s en échec : %s' % (command.get('name'), error),
                                  command=shown, trace=traceback.format_exc())
                self.command_results.append(result)
        if self.command_results:
            report = self.odoo().call('push', {'agent': agent_info(), 'records': [], 'report_only': True,
                                               'command_results': self.command_results})
            if report.get('ok'):
                self.command_results = []
        message = '%s nouveau(x) pointage(s) envoyé(s).' % created if created else 'À jour.'
        if self.status['unknown']:
            message += ' Identifiants sans employé dans Odoo : %s.' % ', '.join(self.status['unknown'])
        self.status.update(state='warning' if self.status['unknown'] else 'ok', message=message,
                           last_success=now_str())

    def poll_pending(self):
        """Ask Odoo (cheap call) whether a request waits: user update, synchronisation..."""
        now = time.monotonic()
        if (not self.config.get('enabled', True) or self.status.get('state') == 'error'
                or self.next_run - now <= POLL_SECONDS or now - self.last_poll < POLL_SECONDS):
            return
        self.last_poll = now
        try:
            hello = self.odoo().call('hello', {'agent': agent_info()})
        except Exception:
            return  # the regular synchronisation reports connection problems
        if hello.get('pending'):
            self.journal.debug('odoo', 'Demande en attente dans Odoo : synchronisation immédiate.')
            self.next_run = 0.0

    def run_if_due(self, force=False):
        if not self.config.get('enabled', True):
            self.status.update(state='paused', message='Synchronisation suspendue.')
            return
        if not force and time.monotonic() < self.next_run:
            return
        try:
            with self.lock:
                self.cycle()
            self.next_run = time.monotonic() + self.interval
        except Exception as error:
            self.status.update(state='error', message=str(error))
            category = 'odoo' if isinstance(error, OdooError) else 'device'
            self.journal.error(category, 'Synchronisation impossible : %s' % error,
                               steps=getattr(self, 'steps', []), trace=traceback.format_exc())
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
                worker.poll_pending()
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
    # Token -> expiry timestamp. Tokens only live in memory, so restarting the
    # gateway also invalidates every console session.
    sessions = {}

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
                if name == 'pt_relay_session':
                    expires_at = sessions.get(value)
                    if expires_at and expires_at > time.monotonic():
                        return value
                    sessions.pop(value, None)
            return None

        @staticmethod
        def _expired_session_cookie():
            return 'pt_relay_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'

        def _new_session(self):
            session = secrets.token_urlsafe(24)
            sessions[session] = time.monotonic() + SESSION_TTL_SECONDS
            return session

        def _session_cookie(self, session):
            return ('pt_relay_session=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%s'
                    % (session, SESSION_TTL_SECONDS))

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
                session = self._new_session()
                return self._send(200, {'ok': True}, headers={
                    'Set-Cookie': self._session_cookie(session)})
            if route == '/api/lock':
                session = self._session()
                if session:
                    sessions.pop(session, None)
                return self._send(200, {'ok': True}, headers={
                    'Set-Cookie': self._expired_session_cookie()})
            if route == '/api/sync':
                engine.sync_now(payload.get('id'))
                return self._send(200, {'ok': True})
            if not self._unlocked():
                return self._send(401, {'error': 'Console verrouillée : saisissez le code PIN.'})
            try:
                return self._send(200, self.dispatch(route, payload))
            except DeviceBusy as error:
                return self._send(409, {'error': 'Pointeuse occupée : %s. Réessayez dans quelques secondes.' % error})
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
            if route.startswith('/api/device/') and route not in (
                    '/api/device/test', '/api/device/save', '/api/device/remove'):
                return self.device_route(route, payload)
            if route == '/api/scan':
                return dict(scan_devices(int(payload.get('port') or 4370)), ok=True)
            if route == '/api/pin':
                current_pin = str(payload.get('current_pin') or '').strip()
                pin = str(payload.get('pin') or '').strip()
                confirmation = str(payload.get('confirmation') or '').strip()
                if config.data.get('pin_hash') and not config.check_pin(current_pin):
                    time.sleep(1)
                    return self._send(403, {'error': 'Code PIN actuel incorrect.'})
                if pin != confirmation:
                    return self._send(400, {'error': 'Les deux nouveaux codes PIN ne correspondent pas.'})
                if pin and (not pin.isdigit() or not 4 <= len(pin) <= 12):
                    return self._send(400, {'error': 'Le PIN doit contenir 4 à 12 chiffres.'})
                config.set_pin(pin)
                sessions.clear()
                _logger.info('Code PIN de la console %s.', 'défini' if pin else 'supprimé')
                # Changing the PIN always logs out every browser, including the
                # one that made the change. The new PIN must be entered again.
                return self._send(200, {'ok': True}, headers={
                    'Set-Cookie': self._expired_session_cookie()})
            raise KeyError('route inconnue %s' % route)

        def device_route(self, route, payload):
            worker = engine.workers.get(payload.get('id'))
            if not worker:
                raise KeyError('pointeuse inconnue')
            if route == '/api/device/logs':
                # Reading the journal does not touch the device: no lock needed.
                return dict(worker.journal.read(
                    level=payload.get('level') or '', category=payload.get('category') or '',
                    day=payload.get('day') or '', query=payload.get('q') or '',
                    offset=int(payload.get('offset') or 0), limit=min(int(payload.get('limit') or 200), 1000)),
                    ok=True)
            if not worker.lock.acquire(timeout=90):
                raise DeviceBusy('la pointeuse est en cours de synchronisation, réessayez dans un instant')
            try:
                device = worker.device()
                if route == '/api/device/users':
                    users, info = device.list_users()
                    numeric = [int(user['user_id']) for user in users if user['user_id'].isdigit()]
                    return {'ok': True, 'users': users, 'info': info,
                            'next_id': str(max(numeric) + 1 if numeric else 1),
                            'mapping': worker.status.get('mapping') or {},
                            'mapping_known': 'mapping' in worker.status}
                if route == '/api/device/punches':
                    punches = device.list_punches()
                    return {'ok': True, 'total': len(punches), 'punches': punches[:20000]}
                if route == '/api/device/user/save':
                    user_id = str(payload.get('user_id') or '').strip()
                    user_name = str(payload.get('name') or '').strip()
                    password = str(payload.get('password') or '').strip()
                    card = str(payload.get('card') or '0').strip() or '0'
                    if not user_id.isdigit() or len(user_id) > 9:
                        raise ValueError("L'identifiant doit être un nombre de 1 à 9 chiffres.")
                    if not user_name or len(user_name) > 24:
                        raise ValueError('Le nom est obligatoire (24 caractères au maximum).')
                    if not card.isdigit():
                        raise ValueError('Le numéro de carte doit être numérique.')
                    if password and (not password.isdigit() or len(password) > 8):
                        raise ValueError('Le mot de passe doit contenir au plus 8 chiffres.')
                    if payload.get('new'):
                        users, _info = device.list_users()
                        if any(user['user_id'] == user_id for user in users):
                            raise ValueError("L'identifiant %s est déjà utilisé sur la pointeuse." % user_id)
                    result = device.user_command({
                        'name': 'push_user', 'user_id': user_id, 'user_name': user_name,
                        'privilege': 14 if str(payload.get('privilege')) == '14' else 0,
                        'password': password, 'card': int(card)})
                    worker.journal.info('console', 'Console : %s' % result['message'],
                                        user={'user_id': user_id, 'name': user_name, 'card': card,
                                              'privilege': payload.get('privilege')})
                    engine.sync_now(payload['id'])
                    return dict(result, ok=True)
                if route == '/api/device/user/delete':
                    result = device.user_command({'name': 'remove_user', 'user_id': str(payload['user_id'])})
                    worker.journal.info('console', 'Console : %s' % result['message'])
                    engine.sync_now(payload['id'])
                    return dict(result, ok=True)
                if route == '/api/device/action':
                    action = payload.get('action')
                    if action == 'set_time':
                        message = device.run_command({'name': 'set_time', 'value': now_str()})
                    elif action == 'restart':
                        message = device.run_command({'name': 'restart'})
                    elif action == 'clear_attendance':
                        # Never lose a punch: send everything to Odoo first.
                        worker.cycle()
                        message = device.run_command({'name': 'clear_attendance'})
                        message += ' Les pointages avaient été envoyés à Odoo juste avant.'
                    elif action == 'info':
                        return {'ok': True, 'info': device.probe(), 'pc_time': now_str()}
                    else:
                        raise ValueError('action inconnue')
                    worker.journal.info('console', 'Console : %s' % message, action=action)
                    return {'ok': True, 'message': message}
                raise KeyError('route inconnue %s' % route)
            finally:
                worker.lock.release()

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
.lock-button{width:36px;height:36px;padding:0;display:grid;place-items:center;background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;border-radius:8px}.lock-button:hover{background:#e2e8f0;color:#1e293b}.lock-button:disabled{opacity:.55}.lock-button svg{width:17px;height:17px;fill:currentColor}
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
.modal.wide{width:min(1100px,100%);padding:0}
.mhead{padding:20px 24px 0;position:sticky;top:0;background:#fff;z-index:2;border-bottom:1px solid var(--line)}
.mhead .title{display:flex;align-items:center;gap:10px;justify-content:space-between}
.mhead h2{margin:0}.mbody{padding:18px 24px 24px}
.tabs{display:flex;gap:4px;margin-top:14px}
.tabs button{border:0;border-bottom:3px solid transparent;border-radius:0;padding:10px 14px;background:none;font-weight:600;color:var(--muted)}
.tabs button.on{color:var(--brand);border-bottom-color:var(--brand)}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
.bar input,.bar select{width:auto;flex:1;min-width:170px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.stat{background:linear-gradient(135deg,#f5f3ff,#fff);border:1px solid #ede9fe;border-radius:12px;padding:10px 14px}
.stat b{display:block;font-size:22px;color:var(--brand)}.stat span{font-size:12px;color:var(--muted)}
table.data{width:100%;border-collapse:separate;border-spacing:0;font-size:14px}
table.data th{position:sticky;top:0;background:#f9fafb;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);padding:9px 10px;border-bottom:1px solid var(--line)}
table.data td{padding:9px 10px;border-bottom:1px solid #f1f2f4}
table.data tr:hover td{background:#faf8ff}
.tablewrap{max-height:52vh;overflow:auto;border:1px solid var(--line);border-radius:12px}
.avatar{width:30px;height:30px;border-radius:50%;display:inline-grid;place-items:center;font-size:12px;font-weight:700;color:#fff;margin-right:8px;vertical-align:middle}
.tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;background:#f3f4f6;color:#374151}
.tag.admin{background:#fef3c7;color:#92400e}.tag.face{background:#e0f2fe;color:#075985}.tag.finger{background:#ede9fe;color:#5b21b6}
.tag.card{background:#dcfce7;color:#166534}.tag.pwd{background:#fee2e2;color:#991b1b}
.iconbtn{padding:5px 9px;border-radius:8px}
.formcard{border:1px solid #ddd6fe;background:#faf8ff;border-radius:12px;padding:14px 16px;margin-bottom:14px;animation:enter .2s ease both}
.formcard .row{flex-wrap:wrap}.formcard .row>*{min-width:140px}
.daysep td{background:#f5f3ff!important;font-weight:700;color:var(--brand);font-size:13px}
.infogrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.infogrid div{background:#f9fafb;border-radius:10px;padding:10px 12px}.infogrid span{display:block;font-size:12px;color:var(--muted)}
.meter{height:6px;background:#e5e7eb;border-radius:9px;margin-top:6px;overflow:hidden}.meter i{display:block;height:100%;background:var(--brand);border-radius:9px}
.actions-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:16px}
.action{border:1px solid var(--line);border-radius:12px;padding:12px 14px}.action p{margin:4px 0 10px;font-size:13px;color:var(--muted)}
.loading{padding:40px;text-align:center;color:var(--muted)}
.lvl{display:inline-block;min-width:92px;text-align:center;padding:2px 8px;border-radius:99px;font-size:11.5px;font-weight:700;letter-spacing:.03em}
.lvl.DEBUG{background:#f3f4f6;color:#6b7280}.lvl.INFO{background:#e0f2fe;color:#075985}
.lvl.WARNING{background:#fef3c7;color:#92400e}.lvl.ERROR{background:#fee2e2;color:#991b1b}
table.journal td{vertical-align:top;font-size:13.5px}table.journal td.t{white-space:nowrap;font:12.5px Consolas,monospace;color:#374151}
table.journal tr.ERROR td{background:#fff7f7}table.journal tr.clickable{cursor:pointer}
.detail{background:#0f172a;color:#e2e8f0;font:12px/1.55 Consolas,monospace;white-space:pre-wrap;word-break:break-word;border-radius:10px;padding:10px 12px;margin-top:8px;max-height:260px;overflow:auto}
.live{display:inline-flex;align-items:center;gap:8px;margin:0;font-size:13px;font-weight:500;color:var(--muted)}.live input,.bar .live input{width:auto;flex:none;min-width:0;padding:0;margin:0}
.lasterr{border:1px solid #fecaca;background:#fef2f2;border-radius:12px;padding:10px 14px;margin-bottom:14px;font-size:13.5px;color:#991b1b}
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
  <button id="session-button" class="lock-button" onclick="lockSession()" title="Verrouiller la console" aria-label="Verrouiller la console" hidden><svg viewBox="0 0 16 16"><path d="M11 1a3 3 0 0 0-3 3v2h1V4a2 2 0 1 1 4 0v3H4.5A1.5 1.5 0 0 0 3 8.5v6A1.5 1.5 0 0 0 4.5 16h8a1.5 1.5 0 0 0 1.5-1.5v-6A1.5 1.5 0 0 0 12.5 7H12V4a1 1 0 0 0-1-1H7v1h4v3H4.5A2.5 2.5 0 0 0 2 9.5v5A1.5 1.5 0 0 0 3.5 16h9a2.5 2.5 0 0 0 2.5-2.5v-5A1.5 1.5 0 0 0 13.5 7H14V4a3 3 0 0 0-3-3Z"/></svg></button>
  <span class="pill" id="global"><span class="dot"></span><span>Chargement…</span></span>
</header>
<main id="app"></main>

<div class="modal-back" id="modal"><div class="modal" id="modal-body"></div></div>

<script>
const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null;
let wizard = null;
let pinDraft = '';
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
      <button onclick="openManage('${c.id}')">👥 Gérer</button>
      <button onclick="openManage('${c.id}', 'logs')">📜 Journal</button>
      <button onclick="editDevice('${c.id}')">⚙ Paramètres</button>
      <button onclick="toggleDevice('${c.id}', ${c.enabled === false})">${c.enabled === false ? '▶ Reprendre' : '⏸ Suspendre'}</button>
      <button class="danger" onclick="removeDevice('${c.id}')">✕ Retirer</button>
    </div>
  </div>`;
}

function render() {
  if (!state) return;
  $('#session-button').hidden = !state.unlocked;
  if (state.unlocked) {
    $('#session-button').textContent = '🔓';
    $('#session-button').disabled = false;
  }
  $('#host').textContent = `PC ${state.host} · version ${state.version} · démarrée le ${state.started_at}`;
  const states = state.devices.map((d) => d.status.state);
  const globalState = !states.length ? '' : states.includes('error') ? 'error' : states.includes('warning') ? 'warning' : 'ok';
  const label = !states.length ? 'Aucune pointeuse' : globalState === 'error' ? 'Attention requise' : 'Opérationnelle';
  $('#global').innerHTML = `<span class="dot ${globalState}"></span><span>${label}</span>`;
  if (!state.unlocked) {
    $('#app').innerHTML = `<div class="card lock"><div style="font-size:40px">🔒</div><h3 style="justify-content:center">Console verrouillée</h3>
      <p class="help">Saisissez le code PIN administrateur pour modifier la passerelle. La synchronisation continue en arrière-plan.</p>
      <input type="password" id="pin" value="${esc(pinDraft)}" placeholder="Code PIN" autocomplete="current-password"
             oninput="pinDraft=this.value" onkeydown="if(event.key==='Enter')unlock()">
      <div class="actions" style="justify-content:center"><button class="primary" onclick="unlock()">Déverrouiller</button></div>
      <div id="pin-note"></div></div>`;
    return;
  }
  const devices = state.devices.length
    ? `<div class="grid">${state.devices.map(deviceCard).join('')}</div>`
    : `<div class="card empty"><div class="big">🔗</div><h3 style="justify-content:center">Aucune pointeuse associée</h3>
       <p>Associez cette passerelle à votre serveur Odoo pour envoyer les pointages automatiquement.</p>
       <button class="primary" onclick="openWizard()">＋ Ajouter une pointeuse</button></div>`;
  const logs = state.logs.slice().reverse().map((l) => `<div class="${esc(l.level)}">${esc(l.last_time || l.time)}  ${esc(l.message)}${l.repeat ? `  <b>×${l.repeat}</b> <span style="opacity:.6">(depuis ${esc(l.time)})</span>` : ''}</div>`).join('');
  $('#app').innerHTML = `
    <div class="toolbar"><h2>Pointeuses</h2>
      <button onclick="syncNow()">⟳ Tout synchroniser</button>
      <button onclick="openPin()">🔒 ${state.has_pin ? 'Changer le PIN' : 'Protéger par PIN'}</button>
      <button class="primary" onclick="openWizard()">＋ Ajouter une pointeuse</button></div>
    ${devices}
    <div class="logs">${logs || 'Journal vide.'}</div>`;
}

async function refresh() {
  try {
    state = await api('/api/state');
    // Do not rebuild the lock screen while the PIN field has focus: rebuilding
    // it every three seconds discarded characters entered by the user.
    if (!$('#modal').classList.contains('open') && !( !state.unlocked && document.activeElement?.id === 'pin')) render();
  }
  catch (error) { $('#global').innerHTML = '<span class="dot error"></span><span>Service arrêté</span>'; }
}

async function unlock() {
  const input = $('#pin');
  if (!input) return;
  pinDraft = input.value;
  try { await api('/api/unlock', {pin: pinDraft}); pinDraft = ''; await refresh(); }
  catch (error) {
    const note = $('#pin-note');
    if (note) note.innerHTML = `<div class="note err">${esc(error.message)}</div>`;
  }
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
  const current = state.has_pin ? `<label>Code PIN actuel</label><input type="password" id="current-pin" inputmode="numeric" maxlength="12" autocomplete="current-password">` : '';
  openModal(`<h2>Code PIN administrateur</h2>
    <p class="help">Le PIN protège les réglages de la passerelle. Sa modification déconnecte toutes les sessions. Laissez les deux nouveaux champs vides pour retirer la protection.</p>
    ${current}
    <label>Nouveau code PIN</label><input type="password" id="new-pin" maxlength="12" placeholder="4 à 12 chiffres">
    <label>Confirmer le nouveau code PIN</label><input type="password" id="confirm-pin" maxlength="12" inputmode="numeric">
    <div id="pin-msg"></div>
    <div class="footer"><button onclick="closeModal()">Annuler</button><button class="primary" onclick="savePin()">Enregistrer</button></div>`);
}
async function savePin() {
  const pin = $('#new-pin').value.trim();
  const confirmation = $('#confirm-pin').value.trim();
  const current = $('#current-pin') ? $('#current-pin').value.trim() : '';
  if (pin && !/^\d{4,12}$/.test(pin)) return note('#pin-msg', 'err', 'Le PIN doit contenir 4 à 12 chiffres.');
  if (pin !== confirmation) return note('#pin-msg', 'err', 'Les deux nouveaux codes PIN ne correspondent pas.');
  try { await api('/api/pin', {current_pin: current, pin, confirmation}); pinDraft = ''; closeModal(); }
  catch (error) { note('#pin-msg', 'err', esc(error.message)); }
}

async function lockSession() {
  $('#session-button').textContent = '🔒';
  $('#session-button').disabled = true;
  $('#session-button').hidden = true;
  try { await api('/api/lock', {}); pinDraft = ''; closeModal(); await refresh(); }
  catch (error) { alert(error.message); }
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


// ---------------------------------------------------------------- device management
const METHODS = {0: ['Mot de passe', 'pwd'], 1: ['Empreinte', 'finger'], 2: ['Carte', 'card'], 3: ['Mot de passe', 'pwd'], 4: ['Carte', 'card'], 15: ['Visage', 'face']};
const PUNCHES = {0: 'Entrée', 1: 'Sortie', 2: 'Début pause', 3: 'Fin pause', 4: 'Entrée H. sup.', 5: 'Sortie H. sup.'};
const COLORS = ['#7c3aed', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626', '#db2777', '#4f46e5'];
let manage = null;

function avatar(name, id) {
  const initials = (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
  const color = COLORS[(Number(id) || 0) % COLORS.length];
  return `<span class="avatar" style="background:${color}">${esc(initials)}</span>`;
}
function fmtDate(iso) { const [d, t] = iso.split(' '); const [y, m, j] = d.split('-'); return {day: `${j}/${m}/${y}`, time: t.slice(0, 5), iso: d}; }
function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }

function openManage(id, tab = 'users') {
  const item = state.devices.find((d) => d.config.id === id);
  manage = {id, name: item.config.name, tab, users: null, punches: null, info: null, q: '', day: '', edit: null, limit: 300,
            log: {level: 'INFO', category: '', day: '', q: '', limit: 200, live: true, open: null, data: null}};
  $('#modal-body').classList.add('wide');
  renderManage();
  loadTab();
}
function closeManage() { manage = null; $('#modal-body').classList.remove('wide'); closeModal(); }
setInterval(() => { if (manage && manage.tab === 'logs' && manage.log.live && !manage.log.open) loadLogs(true); }, 5000);

function renderManage() {
  const tabs = [['users', '👥 Utilisateurs'], ['punches', '🕒 Pointages'], ['device', '🛠 Appareil'], ['logs', '📜 Journal']];
  openModal(`<div class="mhead"><div class="title"><h2>${esc(manage.name)}</h2><button onclick="closeManage()">✕ Fermer</button></div>
    <div class="tabs">${tabs.map(([key, label]) => `<button class="${manage.tab === key ? 'on' : ''}" onclick="switchTab('${key}')">${label}</button>`).join('')}</div></div>
    <div class="mbody" id="mbody"></div>`);
  renderTab();
}
function switchTab(tab) { manage.tab = tab; manage.edit = null; manage.q = ''; renderManage(); loadTab(); }

async function loadTab(force) {
  const tab = manage.tab;
  try {
    if (tab === 'users' && (force || !manage.users)) {
      manage.users = null; renderTab();
      const result = await api('/api/device/users', {id: manage.id});
      Object.assign(manage, {users: result.users, info: result.info, nextId: result.next_id,
                             mapping: result.mapping || {}, mappingKnown: result.mapping_known});
    } else if (tab === 'punches' && (force || !manage.punches)) {
      manage.punches = null; renderTab();
      const result = await api('/api/device/punches', {id: manage.id});
      Object.assign(manage, {punches: result.punches, total: result.total});
      if (!manage.day && manage.punches.length) manage.day = manage.punches[0].time.slice(0, 10);
    } else if (tab === 'logs') {
      await loadLogs();
      return;
    } else if (tab === 'device' && (force || !manage.info || !manage.pcTime)) {
      manage.info = null; renderTab();
      const result = await api('/api/device/action', {id: manage.id, action: 'info'});
      Object.assign(manage, {info: result.info, pcTime: result.pc_time});
    }
  } catch (error) { manage.error = error.message; }
  if (manage && manage.tab === tab) renderTab();
}

function renderTab() {
  const body = $('#mbody'); if (!body) return;
  if (manage.error) { const message = manage.error; manage.error = null; body.innerHTML = `<div class="note err">${esc(message)}</div><div class="actions"><button onclick="loadTab(true)">Réessayer</button></div>`; return; }
  if (manage.tab === 'users') body.innerHTML = usersTab();
  if (manage.tab === 'punches') body.innerHTML = punchesTab();
  if (manage.tab === 'device') body.innerHTML = deviceTab();
  if (manage.tab === 'logs') body.innerHTML = logsTab();
}
const spinner = (text) => `<div class="loading"><span class="spin"></span> ${text}</div>`;

// ---- users
function usersTab() {
  if (!manage.users) return spinner('Lecture des utilisateurs de la pointeuse…');
  const info = manage.info || {};
  const admins = manage.users.filter((u) => Number(u.privilege) === 14).length;
  const unmapped = manage.mappingKnown ? manage.users.filter((u) => !manage.mapping[u.user_id]).length : null;
  return `<div class="stats">
      <div class="stat"><b>${manage.users.length}</b><span>utilisateurs / ${info.users_cap ?? '?'}</span></div>
      <div class="stat"><b>${admins}</b><span>administrateur(s)</span></div>
      <div class="stat"><b style="${unmapped ? 'color:var(--err)' : ''}">${unmapped ?? '—'}</b><span>sans employé Odoo</span></div>
      <div class="stat"><b>${info.fingers ?? '—'}</b><span>empreintes enregistrées</span></div>
      <div class="stat"><b>${info.faces ?? '—'}</b><span>visages enregistrés</span></div></div>
    ${manage.edit ? userForm() : ''}
    <div class="bar"><input placeholder="🔍 Rechercher par nom ou identifiant…" value="${esc(manage.q)}" oninput="manage.q=this.value;$('#users-table').innerHTML=usersRows()">
      <button onclick="loadTab(true)">⟳ Actualiser</button><button class="primary" onclick="editUser()">＋ Nouvel utilisateur</button></div>
    ${unmapped ? `<div class="note err" style="margin:0 0 12px">⚠ ${unmapped} utilisateur(s) sans employé : leurs pointages ne sont pas importés. Dans Odoo : <b>Gestion des pointages › Pointeuses › Utilisateurs des pointeuses</b>, puis « Associer automatiquement » ou « Créer les employés manquants ».</div>` : ''}
    <div class="note info" style="margin:0 0 12px">Les empreintes et visages s'enregistrent sur la pointeuse (Menu › Utilisateurs › Modifier). Les changements faits ici remontent dans Odoo à la synchronisation suivante.</div>
    <div class="tablewrap"><table class="data"><thead><tr><th>Utilisateur</th><th>Identifiant</th><th>Employé Odoo</th><th>Rôle</th><th>Carte</th><th>Mot de passe</th><th style="text-align:right">Actions</th></tr></thead>
    <tbody id="users-table">${usersRows()}</tbody></table></div>`;
}
function usersRows() {
  const q = manage.q.trim().toLowerCase();
  const rows = manage.users.filter((u) => !q || (u.name || '').toLowerCase().includes(q) || u.user_id.includes(q))
    .sort((a, b) => (Number(a.user_id) || 0) - (Number(b.user_id) || 0));
  if (!rows.length) return `<tr><td colspan="7" class="loading">Aucun utilisateur${q ? ' pour cette recherche' : ''}.</td></tr>`;
  const odoo = (u) => !manage.mappingKnown ? '<span class="tag">après synchro</span>'
    : manage.mapping[u.user_id] ? `<span class="tag card">✓ ${esc(manage.mapping[u.user_id])}</span>`
    : '<span class="tag pwd">Non associé</span>';
  return rows.map((u) => `<tr><td>${avatar(u.name, u.user_id)}<b>${esc(u.name || '(sans nom)')}</b></td><td>${esc(u.user_id)}</td><td>${odoo(u)}</td>
    <td>${Number(u.privilege) === 14 ? '<span class="tag admin">Administrateur</span>' : '<span class="tag">Utilisateur</span>'}</td>
    <td>${u.card ? esc(u.card) : '—'}</td><td>${u.has_password ? '••••' : '—'}</td>
    <td style="text-align:right;white-space:nowrap"><button class="iconbtn" title="Modifier" onclick="editUser('${esc(u.user_id)}')">✎</button>
      <button class="iconbtn danger" title="Supprimer" onclick="deleteUser('${esc(u.user_id)}')">🗑</button></td></tr>`).join('');
}
function editUser(userId) {
  const user = userId ? manage.users.find((u) => u.user_id === userId) : null;
  manage.edit = user ? {...user, isNew: false} : {user_id: manage.nextId || '', name: '', privilege: 0, card: 0, isNew: true};
  renderTab(); setTimeout(() => $('#u-name') && $('#u-name').focus(), 30);
}
function userForm() {
  const u = manage.edit;
  return `<div class="formcard"><b>${u.isNew ? 'Nouvel utilisateur' : 'Modifier ' + esc(u.name)}</b>
    <div class="row"><div><label>Identifiant</label><input id="u-id" value="${esc(u.user_id)}" ${u.isNew ? '' : 'disabled'} maxlength="9"></div>
      <div style="flex:2"><label>Nom (24 caractères max.)</label><input id="u-name" value="${esc(u.name)}" maxlength="24"></div>
      <div><label>Rôle</label><select id="u-role"><option value="0">Utilisateur</option><option value="14" ${Number(u.privilege) === 14 ? 'selected' : ''}>Administrateur</option></select></div></div>
    <div class="row"><div><label>Numéro de carte</label><input id="u-card" value="${u.card ? esc(u.card) : ''}" placeholder="aucune"></div>
      <div><label>Mot de passe (chiffres)</label><input id="u-pwd" type="password" maxlength="8" placeholder="${u.has_password ? 'inchangé si vide' : 'aucun'}"></div></div>
    <div id="u-note"></div>
    <div class="actions"><button onclick="manage.edit=null;renderTab()">Annuler</button><button class="primary" id="u-save" onclick="saveUser()">Enregistrer sur la pointeuse</button></div></div>`;
}
async function saveUser() {
  const button = $('#u-save'); busy(button, true, 'Envoi à la pointeuse…'); note('#u-note');
  const values = {id: manage.id, new: manage.edit.isNew, user_id: $('#u-id').value.trim(), name: $('#u-name').value.trim(),
                  privilege: Number($('#u-role').value), card: $('#u-card').value.trim() || '0', password: $('#u-pwd').value.trim()};
  try {
    const result = await api('/api/device/user/save', values);
    manage.edit = null; toast(result.message); await loadTab(true);
  } catch (error) { note('#u-note', 'err', esc(error.message)); busy(button, false); }
}
async function deleteUser(userId) {
  const user = manage.users.find((u) => u.user_id === userId);
  if (!confirm(`Supprimer « ${user.name} » (identifiant ${userId}) de la pointeuse ?\n\nSes empreintes, son visage et sa carte seront effacés de l'appareil. Ses pointages déjà enregistrés sont conservés.`)) return;
  try { const result = await api('/api/device/user/delete', {id: manage.id, user_id: userId}); toast(result.message); await loadTab(true); }
  catch (error) { alert(error.message); }
}

// ---- punches
function punchesTab() {
  if (!manage.punches) return spinner('Lecture de la mémoire de la pointeuse…');
  const list = filteredPunches();
  const todayRows = manage.punches.filter((p) => p.time.startsWith(today()));
  const people = new Set(todayRows.map((p) => p.user_id)).size;
  const days = [...new Set(manage.punches.map((p) => p.time.slice(0, 10)))];
  return `<div class="stats">
      <div class="stat"><b>${manage.total}</b><span>pointages en mémoire</span></div>
      <div class="stat"><b>${todayRows.length}</b><span>pointages aujourd'hui</span></div>
      <div class="stat"><b>${people}</b><span>personne(s) aujourd'hui</span></div>
      <div class="stat"><b>${list.length}</b><span>affichés (filtre)</span></div></div>
    <div class="bar"><select onchange="manage.day=this.value;manage.limit=300;$('#mbody').innerHTML=punchesTab()">
        <option value="">Tous les jours</option>${days.map((d) => `<option value="${d}" ${d === manage.day ? 'selected' : ''}>${fmtDate(d + ' 00:00').day}${d === today() ? ' (aujourd\'hui)' : ''}</option>`).join('')}</select>
      <input placeholder="🔍 Nom ou identifiant…" value="${esc(manage.q)}" oninput="manage.q=this.value;manage.limit=300;$('#punch-table').innerHTML=punchRows()">
      <button onclick="loadTab(true)">⟳ Actualiser</button><button onclick="exportCsv()">⬇ Exporter (CSV)</button></div>
    <div class="tablewrap"><table class="data"><thead><tr><th>Heure</th><th>Utilisateur</th><th>Identifiant</th><th>Méthode</th><th>Type</th></tr></thead>
    <tbody id="punch-table">${punchRows()}</tbody></table></div>`;
}
function filteredPunches() {
  const q = manage.q.trim().toLowerCase();
  return manage.punches.filter((p) => (!manage.day || p.time.startsWith(manage.day))
    && (!q || (p.name || '').toLowerCase().includes(q) || p.user_id.includes(q)));
}
function punchRows() {
  const list = filteredPunches();
  if (!list.length) return `<tr><td colspan="5" class="loading">Aucun pointage.</td></tr>`;
  let html = '', lastDay = null;
  for (const p of list.slice(0, manage.limit)) {
    const d = fmtDate(p.time);
    if (d.iso !== lastDay) { lastDay = d.iso; html += `<tr class="daysep"><td colspan="5">📅 ${d.day}${d.iso === today() ? ' — aujourd\'hui' : ''}</td></tr>`; }
    const method = METHODS[p.status] || ['Autre', ''];
    html += `<tr><td><b>${d.time}</b></td><td>${avatar(p.name, p.user_id)}${esc(p.name || 'Inconnu')}</td><td>${esc(p.user_id)}</td>
      <td><span class="tag ${method[1]}">${method[0]}</span></td><td>${PUNCHES[p.punch] || '—'}</td></tr>`;
  }
  if (list.length > manage.limit) html += `<tr><td colspan="5" style="text-align:center"><button onclick="manage.limit+=500;$('#punch-table').innerHTML=punchRows()">Afficher plus (${list.length - manage.limit} restants)</button></td></tr>`;
  return html;
}
function exportCsv() {
  const rows = [['Date', 'Heure', 'Identifiant', 'Nom', 'Méthode', 'Type']].concat(filteredPunches().map((p) => {
    const d = fmtDate(p.time); return [d.day, p.time.slice(11), p.user_id, p.name, (METHODS[p.status] || ['Autre'])[0], PUNCHES[p.punch] || ''];
  }));
  const csv = '\ufeff' + rows.map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(';')).join('\r\n');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  link.download = `pointages_${manage.name.replace(/\W+/g, '_')}_${manage.day || 'tous'}.csv`;
  link.click();
}

// ---- device
function deviceTab() {
  if (!manage.info) return spinner('Interrogation de la pointeuse…');
  const i = manage.info;
  const pct = (a, b) => (b ? Math.round(100 * (a || 0) / b) : 0);
  const gauge = (label, a, b) => `<div><span>${label}</span><b>${a ?? '—'} / ${b ?? '—'}</b><div class="meter"><i style="width:${pct(a, b)}%"></i></div></div>`;
  const drift = i.device_time && manage.pcTime ? Math.round((new Date(i.device_time.replace(' ', 'T')) - new Date(manage.pcTime.replace(' ', 'T'))) / 1000) : null;
  return `<div class="infogrid">
      <div><span>Modèle</span><b>${esc(i.device_name || '—')}</b></div><div><span>Numéro de série</span><b>${esc(i.serial || '—')}</b></div>
      <div><span>Firmware</span><b>${esc(i.firmware || '—')}</b></div><div><span>Plateforme · MAC</span><b>${esc(i.platform || '—')}</b><small> ${esc(i.mac || '')}</small></div>
      ${gauge('Utilisateurs', i.users, i.users_cap)}${gauge('Empreintes', i.fingers, i.fingers_cap)}
      ${gauge('Visages', i.faces, i.faces_cap)}${gauge('Pointages en mémoire', i.records, i.records_cap)}
      <div><span>Heure de la pointeuse</span><b>${esc(i.device_time || '—')}</b><small>${drift === null ? '' : (Math.abs(drift) <= 60 ? ' ✓ à l\'heure' : ' ⚠ écart de ' + drift + ' s')}</small></div></div>
    <div class="actions-grid">
      <div class="action"><b>🕒 Régler l'heure</b><p>Met l'horloge de la pointeuse à l'heure de ce PC.</p><button onclick="deviceAction('set_time', this)">Régler maintenant</button></div>
      <div class="action"><b>⟳ Synchroniser</b><p>Envoie immédiatement les nouveaux pointages à Odoo.</p><button onclick="syncNow('${manage.id}');toast('Synchronisation lancée.')">Synchroniser</button></div>
      <div class="action"><b>🧹 Vider la mémoire</b><p>Envoie tout à Odoo, puis efface les pointages de l'appareil. Rien n'est perdu.</p><button class="danger" onclick="deviceAction('clear_attendance', this, 'Envoyer tous les pointages à Odoo puis vider la mémoire de la pointeuse ?')">Vider la mémoire</button></div>
      <div class="action"><b>⏻ Redémarrer</b><p>La pointeuse est indisponible environ une minute.</p><button class="danger" onclick="deviceAction('restart', this, 'Redémarrer la pointeuse ?')">Redémarrer</button></div>
      <div class="action"><b>🔐 Sécuriser par PIN</b><p>Crée ou modifie un administrateur avec PIN : il protège le menu de configuration de la pointeuse.</p><button class="primary" onclick="secureTerminal()">Configurer le PIN</button></div>
    </div><div id="dev-action-note"></div>`;
}
async function secureTerminal() {
  manage.tab = 'users'; renderManage(); await loadTab();
  const admin = manage.users && manage.users.find((user) => Number(user.privilege) === 14);
  if (admin) editUser(admin.user_id);
  else editUser();
}
async function deviceAction(action, button, question) {
  if (question && !confirm(question)) return;
  busy(button, true, 'En cours…'); note('#dev-action-note');
  try { const result = await api('/api/device/action', {id: manage.id, action}); toast(result.message); if (action !== 'restart') await loadTab(true); else busy(button, false); }
  catch (error) { note('#dev-action-note', 'err', esc(error.message)); busy(button, false); }
}


// ---- journal
const LEVELS = {DEBUG: 'Détail', INFO: 'Info', WARNING: 'Avertissement', ERROR: 'Erreur'};
const CATEGORIES = {sync: 'Synchronisation', odoo: 'Odoo', device: 'Pointeuse', command: 'Commande', console: 'Console', config: 'Configuration', service: 'Service'};

async function loadLogs(silent) {
  const log = manage.log;
  try {
    const data = await api('/api/device/logs', {id: manage.id, level: log.level, category: log.category, day: log.day, q: log.q, limit: log.limit});
    log.data = data;
  } catch (error) { manage.error = error.message; }
  if (!manage || manage.tab !== 'logs') return;
  if (silent && $('#log-table')) { $('#log-table').innerHTML = logRows(); $('#log-stats').innerHTML = logStats(); }
  else renderTab();
}
function logStats() {
  const d = manage.log.data, st = d.stats;
  return `<div class="stat"><b>${st.total}</b><span>événements conservés${st.oldest ? ' depuis le ' + esc(st.oldest.slice(0, 10).split('-').reverse().join('/')) : ''}</span></div>
    <div class="stat"><b style="${st.errors_24h ? 'color:var(--err)' : ''}">${st.errors_24h}</b><span>erreur(s) sur 24 h</span></div>
    <div class="stat"><b style="${st.warnings_24h ? 'color:var(--warn)' : ''}">${st.warnings_24h}</b><span>avertissement(s) sur 24 h</span></div>
    <div class="stat"><b>${d.matching}</b><span>correspondant aux filtres</span></div>`;
}
function logsTab() {
  const log = manage.log;
  if (!log.data) return spinner('Lecture du journal…');
  const last = log.data.stats.last_error;
  const opt = (map, value) => Object.entries(map).map(([key, label]) => `<option value="${key}" ${key === value ? 'selected' : ''}>${label}</option>`).join('');
  return `<div class="stats" id="log-stats">${logStats()}</div>
    ${last ? `<div class="lasterr"><b>Dernière erreur</b> — ${esc(last.time.slice(0, 19))} : ${esc(last.message)}</div>` : ''}
    <div class="bar">
      <select onchange="manage.log.level=this.value;loadLogs()"><option value="DEBUG" ${log.level === 'DEBUG' ? 'selected' : ''}>Tous les niveaux (détail compris)</option>${opt({INFO: 'Info et plus', WARNING: 'Avertissements et erreurs', ERROR: 'Erreurs uniquement'}, log.level)}</select>
      <select onchange="manage.log.category=this.value;loadLogs()"><option value="">Toutes les catégories</option>${opt(CATEGORIES, log.category)}</select>
      <input type="date" value="${esc(log.day)}" onchange="manage.log.day=this.value;loadLogs()" style="max-width:170px">
      <input placeholder="🔍 Rechercher dans le journal…" value="${esc(log.q)}" onkeydown="if(event.key==='Enter'){manage.log.q=this.value;loadLogs()}" onblur="if(this.value!==manage.log.q){manage.log.q=this.value;loadLogs()}">
    </div>
    <div class="bar" style="justify-content:space-between">
      <label class="live"><input type="checkbox" ${log.live ? 'checked' : ''} onchange="manage.log.live=this.checked"> Actualisation en direct (5 s)</label>
      <span><button onclick="loadLogs()">⟳ Actualiser</button> <button onclick="exportLogs()">⬇ Exporter</button></span>
    </div>
    <div class="tablewrap"><table class="data journal"><thead><tr><th>Date et heure</th><th>Niveau</th><th>Catégorie</th><th>Événement</th></tr></thead>
    <tbody id="log-table">${logRows()}</tbody></table></div>`;
}
function logRows() {
  const d = manage.log.data;
  if (!d.entries.length) return `<tr><td colspan="4" class="loading">Aucun événement pour ces filtres.</td></tr>`;
  let html = d.entries.map((e, index) => {
    const open = manage.log.open === index;
    const details = e.details ? `<div class="detail">${esc(JSON.stringify(e.details, null, 2).replace(/\\n/g, '\n'))}</div>` : '';
    return `<tr class="${esc(e.level)} ${e.details ? 'clickable' : ''}" ${e.details ? `onclick="manage.log.open=${open ? 'null' : index};$('#log-table').innerHTML=logRows()"` : ''}>
      <td class="t">${esc(e.time.replace(/^(\d{4})-(\d{2})-(\d{2})/, '$3/$2/$1'))}</td>
      <td><span class="lvl ${esc(e.level)}">${LEVELS[e.level] || esc(e.level)}</span></td>
      <td>${CATEGORIES[e.category] || esc(e.category)}</td>
      <td>${esc(e.message)}${e.repeat ? ` <span class="tag" title="Événement identique répété">×${e.repeat}</span> <small style="color:var(--muted)">dernière fois ${esc(e.last_time.slice(11, 19))}${e.last_time.slice(0, 10) !== e.time.slice(0, 10) ? ' le ' + esc(e.last_time.slice(0, 10).split('-').reverse().join('/')) : ''}</small>` : ''}${e.details && !open ? ' <small style="color:var(--muted)">▸ détails</small>' : ''}${open ? details : ''}</td></tr>`;
  }).join('');
  if (d.matching > d.entries.length) html += `<tr><td colspan="4" style="text-align:center"><button onclick="manage.log.limit+=500;loadLogs()">Afficher plus (${d.matching - d.entries.length} plus anciens)</button></td></tr>`;
  return html;
}
async function exportLogs() {
  const log = manage.log;
  const data = await api('/api/device/logs', {id: manage.id, level: log.level, category: log.category, day: log.day, q: log.q, limit: 1000});
  const lines = data.entries.slice().reverse().map((e) => `${e.time}  ${e.level.padEnd(7)}  ${(CATEGORIES[e.category] || e.category).padEnd(16)}  ${e.message}${e.repeat ? `  (x${e.repeat}, dernière fois ${e.last_time})` : ''}${e.details ? '  ' + JSON.stringify(e.details) : ''}`);
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], {type: 'text/plain;charset=utf-8'}));
  link.download = `journal_${manage.name.replace(/\W+/g, '_')}_${new Date().toISOString().slice(0, 10)}.txt`;
  link.click();
}

function toast(message) {
  const box = document.createElement('div');
  box.className = 'note ok'; box.textContent = message;
  Object.assign(box.style, {position: 'fixed', right: '20px', bottom: '20px', zIndex: 50, boxShadow: '0 8px 24px rgba(0,0,0,.15)', maxWidth: '420px'});
  document.body.appendChild(box); setTimeout(() => box.remove(), 4500);
}

function editDevice(id) {
  const item = state.devices.find((d) => d.config.id === id);
  openModal(`<h2>Paramètres de la pointeuse</h2>
    <p class="help">Associée à <b>${esc(item.config.server_url)}</b> (base ${esc(item.config.database)}). Pour changer de serveur, retirez la pointeuse puis associez-la à nouveau.</p>
    ${deviceFields(item.config)}
    <div class="footer"><button onclick="scan()" id="btn-scan">🔍 Rechercher sur le réseau</button>
      <span><button onclick="closeModal()">Annuler</button> <button onclick="testDevice()" id="btn-test">Tester</button> <button class="primary" onclick="finishDevice()">Enregistrer</button></span></div>`);
}

$('#modal').addEventListener('click', (event) => { if (event.target.id === 'modal' && wizard === null && manage === null) closeModal(); });
refresh().then(() => {
  // console.html#ajouter opens the "add a device" wizard directly (link from the installer).
  if (location.hash === '#ajouter' && state && state.unlocked) openWizard();
  const tabs = {'#gerer-utilisateurs': 'users', '#gerer-pointages': 'punches', '#gerer-appareil': 'device', '#gerer-journal': 'logs'};
  if (tabs[location.hash] && state && state.unlocked && state.devices.length) openManage(state.devices[0].config.id, tabs[location.hash]);
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
