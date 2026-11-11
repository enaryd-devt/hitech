# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestDashboardUi(HttpCase):

    def test_dashboard_renders(self):
        employee = self.env['hr.employee'].create({'name': 'Employé tableau de bord', 'device_id_num': '42'})
        yesterday = fields.Date.today() - timedelta(days=1)
        self.env['zk.machine.attendance'].create({
            'employee_id': employee.id,
            'punching_time': datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=9),
            'source': 'manual',
        })
        self.env['biometric.device.details'].create({
            'name': 'Pointeuse UI', 'device_ip': '127.0.0.9', 'port_number': 4370})
        self.browser_js(
            '/odoo/action-primetech_biometric_attendance.action_biometric_attendance_dashboard',
            "console.log('test successful')",
            ready="document.querySelectorAll('.o_pt_bio_kpi').length === 6 "
                  "&& !!document.querySelector('.o_pt_bio_device') "
                  "&& document.querySelectorAll('.o_pt_bio_quick_action').length === 9 "
                  # desktop: every quick action on a single line
                  "&& new Set([...document.querySelectorAll('.o_pt_bio_quick_action')]"
                  ".map((el) => el.offsetTop)).size === 1",
            login='admin',
        )
