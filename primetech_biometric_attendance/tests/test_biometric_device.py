# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class FakeUser:
    def __init__(self, user_id, name, uid=1, privilege=0, card=0):
        self.user_id = user_id
        self.name = name
        self.uid = uid
        self.privilege = privilege
        self.card = card


class FakePunch:
    def __init__(self, user_id, timestamp, punch=255, status=1):
        self.user_id = user_id
        self.timestamp = timestamp
        self.punch = punch
        self.status = status


class FakeConnection:
    def __init__(self, users=None, attendance=None):
        self.users_list = users or []
        self.attendance = attendance or []
        self.disabled = self.enabled = self.cleared = self.disconnected = False

    def disable_device(self):
        self.disabled = True

    def enable_device(self):
        self.enabled = True

    def get_users(self):
        return self.users_list

    def get_attendance(self):
        return self.attendance

    def get_device_name(self):
        return 'K40'

    def clear_attendance(self):
        self.cleared = True
        self.attendance = []

    def disconnect(self):
        self.disconnected = True


@tagged('post_install', '-at_install')
class TestBiometricDevice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The scheduled synchronisation runs as OdooBot, without timezone:
        # the conversion must only depend on the device timezone.
        cls.env.user.tz = False
        cls.device = cls.env['biometric.device.details'].create({
            'name': 'Entrée',
            'device_ip': '127.0.0.1',
            'port_number': 4370,
            'timezone': 'Africa/Douala',
        })
        cls.employee = cls.env['hr.employee'].create({'name': 'Employé connu', 'device_id_num': '10'})

    def connect(self, connection):
        return patch.object(type(self.device), '_connect_device', autospec=True,
                            return_value=connection)

    def test_download_converts_device_timezone_and_deduplicates(self):
        connection = FakeConnection(
            users=[FakeUser('10', 'Employé connu')],
            attendance=[FakePunch('10', datetime(2026, 11, 2, 8, 15))])
        with self.connect(connection):
            self.device._run_synchronization()
            self.device._run_synchronization()
        punches = self.env['zk.machine.attendance'].search([('device_id', '=', self.device.id)])
        self.assertEqual(len(punches), 1)
        self.assertEqual(punches.punching_time, datetime(2026, 11, 2, 7, 15))
        self.assertEqual(punches.source, 'device')
        self.assertTrue(connection.disabled and connection.enabled and connection.disconnected)
        self.assertEqual(self.device.last_sync_state, 'success')
        self.assertTrue(self.device.last_contact_at)

    def test_unknown_users_are_reported_not_created(self):
        connection = FakeConnection(
            users=[FakeUser('99', 'Inconnu')],
            attendance=[FakePunch('99', datetime(2026, 11, 2, 8, 0))])
        with self.connect(connection):
            self.device._run_synchronization()
        self.assertFalse(self.env['hr.employee'].search([('device_id_num', '=', '99')]))
        self.assertEqual(self.device.last_sync_state, 'warning')
        self.assertIn('99', self.device.last_sync_message)

    def test_unknown_users_created_when_enabled(self):
        self.device.create_unknown_employee = True
        connection = FakeConnection(
            users=[FakeUser('98', 'Nouveau')],
            attendance=[FakePunch('98', datetime(2026, 11, 2, 8, 0))])
        with self.connect(connection):
            self.device._run_synchronization()
        employee = self.env['hr.employee'].search([('device_id_num', '=', '98')])
        self.assertEqual(employee.name, 'Nouveau')

    def test_device_mapping_wins_over_employee_number(self):
        other = self.env['hr.employee'].create({'name': 'Autre'})
        self.env['biometric.device.user'].create({
            'device_id': self.device.id, 'employee_id': other.id, 'device_user_id': '10'})
        connection = FakeConnection(attendance=[FakePunch('10', datetime(2026, 11, 2, 8, 0))])
        with self.connect(connection):
            self.device._download_attendance()
        punch = self.env['zk.machine.attendance'].search([('device_id', '=', self.device.id)])
        self.assertEqual(punch.employee_id, other)

    def test_import_users_matches_employees(self):
        connection = FakeConnection(users=[
            FakeUser('10', 'Employé connu', uid=3, privilege=14),
            FakeUser('11', 'Personne', uid=4),
        ])
        with self.connect(connection):
            self.device.action_import_users()
        users = self.env['biometric.device.user'].search([('device_id', '=', self.device.id)])
        self.assertEqual(len(users), 2)
        known = users.filtered(lambda user: user.device_user_id == '10')
        self.assertEqual(known.employee_id, self.employee)
        self.assertEqual(known.privilege, '14')
        self.assertEqual(known.device_uid, 3)
        self.assertFalse(users.filtered(lambda user: user.device_user_id == '11').employee_id)
        self.assertEqual(self.device.unmapped_user_count, 1)

    def test_clear_device_log_keeps_odoo_punches(self):
        connection = FakeConnection(
            users=[FakeUser('10', 'Employé connu')],
            attendance=[FakePunch('10', datetime(2026, 11, 2, 8, 0))])
        with self.connect(connection):
            self.device.action_clear_device_log()
        self.assertTrue(connection.cleared)
        self.assertEqual(self.device.punch_count, 1)

    def test_connection_error_is_recorded(self):
        with patch.object(type(self.device), '_connect_device', autospec=True,
                          side_effect=Exception('timeout')):
            success, message = self.device._run_synchronization()
        self.assertFalse(success)
        self.assertEqual(self.device.last_sync_state, 'error')
        log = self.env['biometric.sync.log'].search([('device_id', '=', self.device.id)])
        self.assertEqual(log.state, 'error')

    def test_import_from_date(self):
        self.device.import_from_date = '2026-11-02'
        connection = FakeConnection(attendance=[
            FakePunch('10', datetime(2026, 11, 1, 8, 0)),
            FakePunch('10', datetime(2026, 11, 2, 8, 0)),
        ])
        with self.connect(connection):
            stats = self.device._download_attendance()
        self.assertEqual(stats['created'], 1)
