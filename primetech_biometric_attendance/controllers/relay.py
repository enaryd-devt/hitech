# -*- coding: utf-8 -*-
"""HTTP endpoints of the local relay (gateway PC reading the device on site)."""
import hmac
import io
import json
import logging
import os
import time
import zipfile

from odoo import SUPERUSER_ID, http
from odoo.http import request
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

RELAY_FILES = (
    ('relay/primetech_zk_relay.py', 'primetech_zk_relay.py'),
    ('relay/installer.bat', 'installer.bat'),
    ('relay/desinstaller.bat', 'desinstaller.bat'),
    ('relay/LISEZMOI.txt', 'LISEZMOI.txt'),
)
RELAY_EXE = 'relay/dist/primetech_zk_relay.exe'


class BiometricRelayController(http.Controller):

    def _json(self, data, status=200):
        return request.make_response(
            json.dumps(data, default=str), status=status,
            headers=[('Content-Type', 'application/json; charset=utf-8')])

    def _relay_device(self):
        header = request.httprequest.headers.get('Authorization') or ''
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        if len(token) < 20:
            return None
        Device = request.env['biometric.device.details'].with_user(SUPERUSER_ID)
        device = Device.search([('relay_token', '=', token), ('active', '=', True)], limit=1)
        if not device or not hmac.compare_digest(device.relay_token or '', token):
            return None
        return device

    @http.route('/primetech_biometric/relay/<string:operation>', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False, readonly=False)
    def relay(self, operation, **kwargs):
        if operation not in ('hello', 'push', 'pair', 'ping'):
            return self._json({'ok': False, 'error': 'Opération inconnue.'}, 404)
        if not request.db:
            return self._json({'ok': False, 'error': 'Base de données non sélectionnée.'}, 400)
        if operation == 'ping':
            # Lets the gateway check that this database runs the attendance module.
            module = request.env['ir.module.module'].with_user(SUPERUSER_ID).search(
                [('name', '=', 'primetech_biometric_attendance')], limit=1)
            return self._json({'ok': True, 'database': request.db,
                               'module_version': module.latest_version})
        if operation == 'pair':
            try:
                payload = json.loads(request.httprequest.get_data() or b'{}')
            except ValueError:
                return self._json({'ok': False, 'error': 'Contenu JSON invalide.'}, 400)
            result = request.env['biometric.device.details'].with_user(SUPERUSER_ID)._relay_pair(payload)
            if not result:
                time.sleep(1)  # slows down code guessing
                return self._json({'ok': False, 'error': (
                    "Code d'association invalide ou expiré. Générez un nouveau code dans Odoo "
                    "(fiche de la pointeuse > Passerelle).")}, 403)
            return self._json(result)
        device = self._relay_device()
        if not device:
            return self._json({'ok': False, 'error': 'Clé de passerelle invalide.'}, 401)
        if device.connection_mode != 'relay':
            return self._json({'ok': False, 'error': (
                'La pointeuse %s est en connexion directe : passez-la en mode '
                '« Passerelle locale » dans Odoo.' % device.name)}, 409)
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return self._json({'ok': False, 'error': 'Contenu JSON invalide.'}, 400)
        if operation == 'hello':
            return self._json(device._relay_hello(payload))
        try:
            return self._json(device._relay_push(payload))
        except Exception as error:
            _logger.exception('Biometric relay push failed for %s', device.display_name)
            request.env.cr.rollback()
            return self._json({'ok': False, 'error': str(error)[:500]}, 500)

    @http.route('/primetech_biometric/relay/package/<int:device_id>', type='http', auth='user')
    def relay_package(self, device_id, **kwargs):
        """Zip with the relay program and its configuration for one device."""
        if not request.env.user.has_group('hr_attendance.group_hr_attendance_manager'):
            return request.not_found()
        device = request.env['biometric.device.details'].browse(device_id).exists()
        if not device:
            return request.not_found()
        device = device.sudo()
        base_url = (request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    or request.httprequest.host_url).rstrip('/')
        config = (
            "; Configuration de la passerelle PrimeTech - %(device)s\n"
            "; Générée par Odoo. Gardez ce fichier confidentiel (il contient la clé).\n\n"
            "[odoo]\n"
            "url = %(url)s\n"
            "database = %(db)s\n"
            "token = %(token)s\n\n"
            "[pointeuse]\n"
            "ip = %(ip)s\n"
            "port = %(port)s\n"
            "cle_communication = %(key)s\n"
            "delai_connexion = %(timeout)s\n\n"
            "[passerelle]\n"
            "; Intervalle par défaut (secondes), remplacé par celui défini dans Odoo.\n"
            "intervalle = %(interval)s\n"
        ) % {
            'device': device.name, 'url': base_url, 'db': request.env.cr.dbname,
            'token': device.relay_token, 'ip': device.device_ip, 'port': device.port_number,
            'key': device.comm_key or 0, 'timeout': device.connection_timeout,
            'interval': max(30, device.sync_interval * 60),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('PrimeTechPointeuse/config.ini', config.replace('\n', '\r\n'))
            for source, target in RELAY_FILES:
                archive.write(file_path('primetech_biometric_attendance/' + source),
                              'PrimeTechPointeuse/' + target)
            try:
                exe = file_path('primetech_biometric_attendance/' + RELAY_EXE)
            except FileNotFoundError:
                exe = None
            if exe and os.path.isfile(exe):
                archive.write(exe, 'PrimeTechPointeuse/primetech_zk_relay.exe')
        filename = 'passerelle_pointeuse_%s.zip' % (device.name or device.id)
        return request.make_response(buffer.getvalue(), headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', http.content_disposition(filename)),
        ])
