# -*- coding: utf-8 -*-
import io
import zipfile
from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestReports(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = 'Africa/Douala'
        cls.device = cls.env['biometric.device.details'].create({
            'name': 'Entrée principale', 'device_ip': '192.168.1.240', 'port_number': 4370,
            'timezone': 'Africa/Douala'})
        cls.employee = cls.env['hr.employee'].create({'name': 'Rapport Test', 'device_id_num': '31'})
        cls.env['biometric.device.user'].create({
            'device_id': cls.device.id, 'employee_id': cls.employee.id, 'device_user_id': '31'})
        cls.env['biometric.device.user'].create({
            'device_id': cls.device.id, 'device_user_id': '32', 'device_user_name': 'Sans employé'})
        Punch = cls.env['zk.machine.attendance']
        for hour in (7, 16):
            Punch.create({'employee_id': cls.employee.id, 'device_id': cls.device.id, 'device_id_num': '31',
                          'punching_time': datetime(2026, 11, 2, hour, 15), 'source': 'device',
                          'attendance_type': '1', 'punch_type': '255'})
        cls.env['biometric.sync.log'].create({'device_id': cls.device.id, 'operation': 'download',
                                              'state': 'error', 'message': 'timeout',
                                              'date': datetime(2026, 11, 2, 9, 0)})
        cls.wizard = cls.env['biometric.attendance.report.wizard'].create({
            'date_from': date(2026, 11, 1), 'date_to': date(2026, 11, 3)})

    def render(self, report_type):
        self.wizard.report_type = report_type
        self.wizard.action_print()  # checks the data and the report action
        report = self.env.ref(self.wizard.REPORT_ACTIONS[report_type])
        html = self.env['ir.actions.report']._render_qweb_html(report.report_name, self.wizard.ids)[0]
        sheets = zipfile.ZipFile(io.BytesIO(self.wizard.build_xlsx())).namelist()
        return html, [name for name in sheets if name.startswith('xl/worksheets/sheet')]

    def test_punches_report(self):
        html, sheets = self.render('punches')
        self.assertIn(b'Rapport Test', html)
        self.assertIn(b'08:15:00', html, 'Times are shown in the user timezone')
        self.assertEqual(len(sheets), 1)

    def test_users_report(self):
        html, sheets = self.render('users')
        self.assertIn(b'Non associ', html)
        self.assertIn(b'Sans employ', html)
        self.assertEqual(len(sheets), 1)

    def test_devices_report(self):
        html, sheets = self.render('devices')
        self.assertIn(b'Entr\xc3\xa9e principale', html)
        self.assertIn(b'timeout', html)
        self.assertEqual(len(sheets), 3)

    def test_attendance_report(self):
        self.env['biometric.attendance.day']._recompute_period(date(2026, 11, 1), date(2026, 11, 3), self.employee)
        html, sheets = self.render('attendance')
        self.assertIn(b'Rapport Test', html)
        self.assertEqual(len(sheets), 2)

    def test_empty_period_is_reported(self):
        wizard = self.env['biometric.attendance.report.wizard'].create({
            'report_type': 'punches', 'date_from': date(2020, 1, 1), 'date_to': date(2020, 1, 2)})
        with self.assertRaises(UserError):
            wizard.action_export_xlsx()

    def test_xlsx_download(self):
        self.authenticate('admin', 'admin')
        wizard = self.env['biometric.attendance.report.wizard'].with_user(self.env.ref('base.user_admin')).create({
            'report_type': 'punches', 'date_from': date(2026, 11, 1), 'date_to': date(2026, 11, 3)})
        response = self.url_open(wizard.action_export_xlsx()['url'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response.headers['Content-Type'])
        self.assertTrue(response.content.startswith(b'PK'))
