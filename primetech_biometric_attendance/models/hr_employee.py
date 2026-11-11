# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author:  Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models


class HrEmployee(models.Model):
    """Biometric identity, attendance schedule and day plan of an employee."""
    _inherit = 'hr.employee'

    device_id_num = fields.Char(string='Identifiant biométrique',
                                help="Identifiant de l'employé sur la pointeuse")
    biometric_device_user_ids = fields.One2many(
        'biometric.device.user', 'employee_id', string='Comptes sur les pointeuses',
        groups='hr_attendance.group_hr_attendance_manager')
    biometric_tracked = fields.Boolean(
        string='Suivi par pointeuse', compute='_compute_biometric_tracked',
        store=True, readonly=False,
        groups='hr_attendance.group_hr_attendance_manager',
        help="Seuls les employés suivis apparaissent comme absents lorsqu'ils "
             "n'ont pas pointé un jour travaillé.")
    biometric_schedule_id = fields.Many2one(
        'biometric.attendance.schedule', string='Horaire de pointage',
        groups='hr_attendance.group_hr_attendance_manager',
        help="Laissez vide pour utiliser l'horaire du département ou celui de la société.")
    biometric_effective_schedule_id = fields.Many2one(
        'biometric.attendance.schedule', string='Horaire appliqué',
        compute='_compute_biometric_effective_schedule_id',
        groups='hr_attendance.group_hr_attendance_manager')
    biometric_day_count = fields.Integer(
        compute='_compute_biometric_day_count',
        groups='hr_attendance.group_hr_attendance_manager')

    @api.depends('device_id_num', 'biometric_device_user_ids')
    def _compute_biometric_tracked(self):
        for employee in self:
            employee.biometric_tracked = bool(
                employee.biometric_tracked or employee.device_id_num
                or employee.biometric_device_user_ids)

    @api.depends('biometric_schedule_id', 'department_id.biometric_schedule_id',
                 'company_id.biometric_default_schedule_id')
    def _compute_biometric_effective_schedule_id(self):
        for employee in self:
            employee.biometric_effective_schedule_id = employee._get_biometric_schedule()

    def _compute_biometric_day_count(self):
        groups = self.env['biometric.attendance.day']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in groups}
        for employee in self:
            employee.biometric_day_count = counts.get(employee.id, 0)

    def _get_biometric_schedule(self):
        """Employee schedule, else the closest department's, else the company's."""
        self.ensure_one()
        employee = self.sudo()
        if employee.biometric_schedule_id:
            return employee.biometric_schedule_id
        department = employee.department_id
        while department:
            if department.biometric_schedule_id:
                return department.biometric_schedule_id
            department = department.parent_id
        return employee.company_id.biometric_default_schedule_id

    def _get_biometric_tz(self):
        self.ensure_one()
        schedule = self._get_biometric_schedule()
        return schedule.timezone if schedule else self.sudo()._get_tz()

    def _get_biometric_day_plan(self, day):
        """Return ``(tz_name, plan)`` for one local date.

        ``plan`` is ``None`` on rest days, otherwise a dict describing the
        expected hours and the tolerances used to analyse the punches.
        """
        self.ensure_one()
        employee = self.sudo()
        schedule = employee._get_biometric_schedule()
        if schedule:
            line = schedule._get_line(day.weekday())
            if not line:
                return schedule.timezone, None
            return schedule.timezone, {
                'source': 'schedule',
                'schedule_id': schedule.id,
                'start': line.planned_start,
                'end': line.planned_end,
                'break_start': line.break_start,
                'break_end': line.break_end,
                'planned_hours': line.planned_hours,
                'grace': schedule.grace_minutes,
                'late_mode': schedule.late_count_mode,
                'early_tolerance': schedule.early_leave_tolerance,
                'overtime_threshold': schedule.overtime_threshold,
                'enforce_windows': schedule.enforce_windows,
                'check_in_window': (line.check_in_from, line.check_in_until),
                'check_out_window': (line.check_out_from, line.check_out_until),
            }
        tz_name = employee._get_biometric_tz()
        calendar = employee.resource_calendar_id
        if (not employee.company_id.biometric_use_resource_calendar or not calendar
                or calendar.flexible_hours):
            return tz_name, None
        week_type = str(self.env['resource.calendar.attendance'].get_week_type(day))
        lines = calendar.attendance_ids.filtered(
            lambda att: att.dayofweek == str(day.weekday())
            and att.day_period != 'lunch' and not att.display_type
            and (not calendar.two_weeks_calendar or att.week_type == week_type)
            and (not att.date_from or att.date_from <= day)
            and (not att.date_to or att.date_to >= day)
        ).sorted('hour_from')
        if not lines:
            return tz_name, None
        start, end = lines[0].hour_from, max(lines.mapped('hour_to'))
        break_start = break_end = 0.0
        if len(lines) > 1 and lines[1].hour_from > lines[0].hour_to:
            break_start, break_end = lines[0].hour_to, lines[1].hour_from
        return tz_name, {
            'source': 'calendar',
            'schedule_id': False,
            'start': start,
            'end': end,
            'break_start': break_start,
            'break_end': break_end,
            'planned_hours': sum(lines.mapped('duration_hours')),
            'grace': 0,
            'late_mode': 'from_start',
            'early_tolerance': 0,
            'overtime_threshold': 0,
            'enforce_windows': False,
            'check_in_window': (0.0, 23.99),
            'check_out_window': (0.0, 23.99),
        }

    def action_view_biometric_days(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.biometric_attendance_day_action')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'search_default_this_month': 1}
        return action
