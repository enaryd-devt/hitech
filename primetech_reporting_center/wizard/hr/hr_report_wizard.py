# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PrimeTechHRReportWizard(models.TransientModel):
    _name = 'primetech.hr.report.wizard'
    _description = 'Assistant rapports Ressources Humaines'

    report_type = fields.Selection([
        ('headcount', 'Effectif'), ('performance', 'Performance du personnel'), ('attendance', 'Présences'),
        ('leave', 'Congés'), ('late_absence', 'Retards et absences'), ('payroll_mass', 'Masse salariale'),
        ('payslip', 'Bulletins de paie')], required=True, default=lambda self: self.env.context.get('default_report_type', 'headcount'))
    date_from = fields.Date(default=lambda self: fields.Date.today().replace(day=1), required=True)
    date_to = fields.Date(default=fields.Date.today, required=True)
    department_id = fields.Many2one('hr.department', string='Département')
    employee_id = fields.Many2one('hr.employee', string='Employé')
    include_inactive = fields.Boolean(string='Inclure les employés archivés')
    group_by_department = fields.Boolean(string='Regrouper par département', default=True)

    def _domain_employee(self):
        domain = []
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.employee_id:
            domain.append(('id', '=', self.employee_id.id))
        return domain

    def _prepare_filters(self):
        self.ensure_one()
        return {'report_type': self.report_type, 'date_from': fields.Date.to_string(self.date_from), 'date_to': fields.Date.to_string(self.date_to), 'department_id': self.department_id.id or False, 'employee_id': self.employee_id.id or False, 'include_inactive': self.include_inactive, 'group_by_department': self.group_by_department}

    def _get_report_title(self):
        return dict(self._fields['report_type'].selection).get(self.report_type, 'Rapport RH')

    def _get_lines(self):
        self.ensure_one()
        Employee = self.env['hr.employee'].with_context(active_test=not self.include_inactive)
        employees = Employee.search(self._domain_employee(), order='department_id, name')
        lines = []
        if self.report_type in ['headcount', 'performance']:
            for employee in employees:
                lines.append({'name': employee.name, 'department': employee.department_id.display_name or 'Non affecté', 'job': employee.job_title or '', 'metric': 'Actif' if employee.active else 'Archivé', 'amount': 0})
        elif self.report_type in ['attendance', 'late_absence'] and 'hr.attendance' in self.env.registry:
            attendances = self.env['hr.attendance'].search([('check_in', '>=', self.date_from), ('check_in', '<=', self.date_to)] + ([('employee_id.department_id', '=', self.department_id.id)] if self.department_id else []) + ([('employee_id', '=', self.employee_id.id)] if self.employee_id else []), order='check_in desc')
            for attendance in attendances:
                hours = attendance.worked_hours if 'worked_hours' in attendance._fields else 0
                lines.append({'name': attendance.employee_id.name, 'department': attendance.employee_id.department_id.display_name or '', 'job': attendance.check_in.strftime('%d/%m/%Y %H:%M') if attendance.check_in else '', 'metric': 'Pointage incomplet' if not attendance.check_out else 'Présent', 'amount': hours})
        elif self.report_type == 'leave' and 'hr.leave' in self.env.registry:
            leaves = self.env['hr.leave'].search([('request_date_from', '<=', self.date_to), ('request_date_to', '>=', self.date_from)] + ([('employee_id.department_id', '=', self.department_id.id)] if self.department_id else []) + ([('employee_id', '=', self.employee_id.id)] if self.employee_id else []), order='request_date_from desc')
            for leave in leaves:
                lines.append({'name': leave.employee_id.name, 'department': leave.employee_id.department_id.display_name or '', 'job': leave.holiday_status_id.display_name, 'metric': dict(leave._fields['state'].selection).get(leave.state, leave.state), 'amount': leave.number_of_days})
        elif self.report_type in ['payroll_mass', 'payslip'] and 'hr.payslip' in self.env.registry:
            payslips = self.env['hr.payslip'].search([('date_from', '>=', self.date_from), ('date_to', '<=', self.date_to)] + ([('employee_id.department_id', '=', self.department_id.id)] if self.department_id else []) + ([('employee_id', '=', self.employee_id.id)] if self.employee_id else []), order='date_from desc')
            for slip in payslips:
                total = sum(slip.line_ids.mapped('total')) if 'line_ids' in slip._fields else 0
                lines.append({'name': slip.employee_id.name, 'department': slip.employee_id.department_id.display_name or '', 'job': slip.name or '', 'metric': dict(slip._fields['state'].selection).get(slip.state, slip.state), 'amount': total})
        return lines

    def get_report_values(self):
        self.ensure_one()
        lines = self._get_lines()
        return {'title': self._get_report_title(), 'wizard': self, 'filters': self._prepare_filters(), 'lines': lines, 'total_amount': sum(line.get('amount') or 0 for line in lines), 'total_lines': len(lines)}

    def action_preview(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_hr_report_preview').report_action(self)

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_hr_report_pdf').report_action(self)

    def action_export_xlsx(self):
        return self.env.ref('primetech_reporting_center.action_hr_report_xlsx').report_action(self, data={'filters': self._prepare_filters()})
