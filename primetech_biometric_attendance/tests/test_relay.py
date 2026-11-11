# -*- coding: utf-8 -*-
import json
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestRelay(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env['biometric.device.details'].create({
            'name': 'Pointeuse distante',
            'device_ip': '192.168.1.250',
            'port_number': 4370,
            'timezone': 'Africa/Douala',
            'connection_mode': 'relay',
        })
        cls.device.action_generate_relay_token()
        cls.employee = cls.env['hr.employee'].create({'name': 'Employé distant', 'device_id_num': '7'})

    def call(self, operation, payload, token=None):
        # Same as the relay: select the database first (several databases may
        # match the server dbfilter).
        self.url_open('/web/login?db=%s' % self.env.cr.dbname)
        response = self.url_open(
            '/primetech_biometric/relay/%s' % operation, data=json.dumps(payload),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer %s' % (token or self.device.relay_token)})
        return response.status_code, response.json()

    def push_payload(self, records, **extra):
        payload = {
            'agent': {'host': 'PC-ACCUEIL', 'version': '1.0.0'},
            'users': [{'user_id': '7', 'name': 'Employe distant', 'uid': 3, 'privilege': 0, 'card': 0},
                      {'user_id': '8', 'name': 'Nouveau', 'uid': 4, 'privilege': 0, 'card': 0}],
            'info': {'serial': 'QME2261200135', 'device_name': 'ZK3969', 'records': len(records),
                     'records_cap': 50000, 'users': 2, 'users_cap': 200},
            'records': records,
        }
        payload.update(extra)
        return payload

    def test_invalid_token_is_rejected(self):
        status, body = self.call('hello', {}, token='x' * 40)
        self.assertEqual(status, 401)
        self.assertFalse(body['ok'])

    def test_hello_then_push(self):
        status, hello = self.call('hello', {'agent': {'host': 'PC-ACCUEIL'}})
        self.assertEqual(status, 200)
        self.assertFalse(hello['since'], 'First synchronisation: the whole memory is expected')

        records = [{'u': '7', 't': '2026-11-02 07:58:00', 's': 1, 'p': 255},
                   {'u': '7', 't': '2026-11-02 17:05:00', 's': 1, 'p': 255},
                   {'u': '8', 't': '2026-11-02 08:10:00', 's': 1, 'p': 255}]
        status, body = self.call('push', self.push_payload(records))
        self.assertEqual(status, 200, body)
        self.assertEqual(body['created'], 2)
        self.assertEqual(body['unknown'], ['8'])
        self.assertTrue(body['since'])

        punches = self.env['zk.machine.attendance'].search([('device_id', '=', self.device.id)])
        self.assertEqual(sorted(punches.mapped('punching_time')),
                         [datetime(2026, 11, 2, 6, 58), datetime(2026, 11, 2, 16, 5)])
        self.assertEqual(self.device.info_serial, 'QME2261200135')
        self.assertEqual(self.device.last_sync_state, 'warning')
        self.assertTrue(self.device.is_online)
        self.assertIn('PC-ACCUEIL', self.device.relay_agent)
        users = self.device.device_user_ids
        self.assertEqual(len(users), 2, 'Device users are imported automatically')
        self.assertEqual(users.filtered(lambda user: user.device_user_id == '7').employee_id, self.employee)

        # A second relay sending the same memory does not create duplicates.
        status, body = self.call('push', self.push_payload(records))
        self.assertEqual(body['created'], 0)

        # Mapping identifier 8 asks the relay to send the whole memory again.
        other = self.env['hr.employee'].create({'name': 'Nouveau'})
        users.filtered(lambda user: user.device_user_id == '8').employee_id = other
        self.assertTrue(self.device.relay_resend_all)
        status, hello = self.call('hello', {})
        self.assertFalse(hello['since'])
        status, body = self.call('push', self.push_payload(records))
        self.assertEqual(body['created'], 1)
        self.assertFalse(self.device.relay_resend_all)

    def test_commands_are_queued_for_the_relay(self):
        self.device.action_set_timezone()
        self.device.action_clear_device_log()
        status, body = self.call('push', self.push_payload([]))
        self.assertEqual([command['name'] for command in body['commands']],
                         ['set_time', 'clear_attendance'])
        self.assertTrue(body['commands'][0]['value'])
        self.assertFalse(self.device.relay_pending_commands)
        status, body = self.call('push', self.push_payload([], command_results=[
            {'command': 'clear_attendance', 'ok': True, 'message': 'Mémoire vidée.'}]))
        self.assertFalse(body['commands'])
        self.assertTrue(self.env['biometric.sync.log'].search([
            ('device_id', '=', self.device.id), ('operation', '=', 'clear'),
            ('state', '=', 'success')]))

    def test_direct_actions_are_refused_in_relay_mode(self):
        with self.assertRaises(UserError):
            self.device.action_test_connection()
        with self.assertRaises(UserError):
            self.device.action_import_users()
        # The scheduled synchronisation ignores relay devices.
        self.env['biometric.device.details'].cron_download()
        self.assertNotEqual(self.device.last_sync_state, 'error')

    def test_direct_device_refuses_relay_calls(self):
        self.device.connection_mode = 'direct'
        status, body = self.call('hello', {})
        self.assertEqual(status, 409)

    def test_package_download(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/primetech_biometric/relay/package/%s' % self.device.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/zip')
        import io
        import zipfile
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = archive.namelist()
        self.assertIn('PrimeTechPointeuse/config.ini', names)
        self.assertIn('PrimeTechPointeuse/installer.bat', names)
        config = archive.read('PrimeTechPointeuse/config.ini').decode('utf-8')
        self.assertIn(self.device.relay_token, config)
        self.assertIn('192.168.1.250', config)
