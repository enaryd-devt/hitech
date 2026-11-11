# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import api, models

from ..models.biometric_attendance_day import PRESENT_STATUSES, float_to_hhmm

DAY_NAMES = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']


class BiometricAttendanceReport(models.AbstractModel):
    _name = 'report.primetech_biometric_attendance.attendance_summary'
    _description = 'Rapport de présence biométrique'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['biometric.attendance.report.wizard'].browse(docids)
        Day = self.env['biometric.attendance.day']
        reports = []
        for wizard in wizards:
            per_employee = OrderedDict()
            for day in wizard._get_days():
                per_employee[day.employee_id] = per_employee.get(day.employee_id, Day) | day
            employees = []
            for employee, days in per_employee.items():
                planned = days.filtered(lambda day: day.plan_source != 'none')
                employees.append({
                    'employee': employee,
                    'days': days,
                    'planned_days': len(planned.filtered(
                        lambda day: day.status not in ('leave', 'holiday'))),
                    'present_days': len(days.filtered(lambda day: day.status in PRESENT_STATUSES)),
                    'absent_days': len(days.filtered(lambda day: day.status == 'absent')),
                    'unjustified_absences': len(days.filtered(
                        lambda day: day.status == 'absent' and not day.justified)),
                    'leave_days': len(days.filtered(lambda day: day.status in ('leave', 'holiday'))),
                    'late_count': len(days.filtered('is_late')),
                    'late_minutes': sum(days.mapped('late_minutes')),
                    'early_minutes': sum(days.mapped('early_leave_minutes')),
                    'overtime_minutes': sum(days.mapped('overtime_minutes')),
                    'incomplete_days': len(days.filtered(
                        lambda day: day.missing_check_in or day.missing_check_out)),
                    'worked_hours': sum(days.mapped('worked_hours')),
                    'planned_hours': sum(planned.mapped('planned_hours')),
                })
            reports.append({'wizard': wizard, 'employees': employees})
        return {
            'doc_ids': docids,
            'doc_model': 'biometric.attendance.report.wizard',
            'docs': wizards,
            'reports': reports,
            'hhmm': float_to_hhmm,
            'minutes_label': lambda minutes: float_to_hhmm((minutes or 0) / 60.0),
            'day_label': lambda day: '%s %s' % (DAY_NAMES[day.weekday()], day.strftime('%d/%m')),
            'status_labels': dict(Day._fields['status'].selection),
        }
