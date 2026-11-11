# -*- coding: utf-8 -*-
from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAccess(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_user = new_test_user(cls.env, login='pt_employe', groups='base.group_user',
                                          name='Employé simple')
        cls.officer_user = new_test_user(
            cls.env, login='pt_agent', name='Agent présences',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer')
        cls.manager_user = new_test_user(
            cls.env, login='pt_responsable', name='Responsable présences',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager')
        Employee = cls.env['hr.employee']
        cls.own_employee = Employee.create({'name': 'Employé simple', 'user_id': cls.employee_user.id})
        cls.colleague = Employee.create({'name': 'Collègue', 'device_id_num': '55'})
        Attendance = cls.env['hr.attendance']
        cls.own_attendance = Attendance.create({
            'employee_id': cls.own_employee.id,
            'check_in': datetime(2026, 11, 2, 7, 0), 'check_out': datetime(2026, 11, 2, 16, 0)})
        cls.colleague_attendance = Attendance.create({
            'employee_id': cls.colleague.id,
            'check_in': datetime(2026, 11, 2, 7, 5), 'check_out': datetime(2026, 11, 2, 16, 5)})

    def menu_xmlids(self, user):
        menus = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
        data = self.env['ir.model.data'].search([('model', '=', 'ir.ui.menu'), ('res_id', 'in', list(menus))])
        return {'%s.%s' % (record.module, record.name) for record in data}

    def test_module_reserved_to_attendance_managers(self):
        for user in (self.employee_user, self.officer_user):
            menus = self.menu_xmlids(user)
            self.assertNotIn('primetech_biometric_attendance.menu_biometric_root', menus)
            self.assertNotIn('primetech_biometric_attendance.menu_hr_attendance_biometric_dashboard', menus)
            for model in ('biometric.attendance.day', 'zk.machine.attendance',
                          'biometric.device.details', 'biometric.attendance.schedule'):
                with self.assertRaises(AccessError, msg='%s / %s' % (user.login, model)):
                    self.env[model].with_user(user).search([])
        menus = self.menu_xmlids(self.manager_user)
        self.assertIn('primetech_biometric_attendance.menu_biometric_root', menus)
        self.env['biometric.attendance.day'].with_user(self.manager_user).search([])

    def test_others_only_see_attendance_overview(self):
        for user in (self.employee_user, self.officer_user):
            menus = self.menu_xmlids(user)
            self.assertIn('hr_attendance.menu_hr_attendance_root', menus)
            self.assertIn('hr_attendance.menu_hr_attendance_view_attendances', menus)
            self.assertNotIn('hr_attendance.menu_hr_attendance_view_attendances_management', menus)
            self.assertNotIn('hr_attendance.menu_hr_attendance_reporting', menus)
            self.assertNotIn('hr_attendance.menu_hr_attendance_settings', menus)
        visible = self.env['hr.attendance'].with_user(self.employee_user).search([])
        self.assertEqual(visible, self.own_attendance)
        with self.assertRaises(AccessError):
            self.own_attendance.with_user(self.employee_user).write({'check_out': datetime(2026, 11, 2, 18, 0)})

    def test_overview_renders_for_employee(self):
        self.browser_js(
            '/odoo/action-hr_attendance.hr_attendance_action',
            "console.log('test successful')",
            ready="!!document.querySelector('.o_list_view') "
                  "&& !document.querySelector('.o_error_dialog')",
            login='pt_employe',
        )
