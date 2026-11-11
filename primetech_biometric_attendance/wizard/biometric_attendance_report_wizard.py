# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BiometricAttendanceReportWizard(models.TransientModel):
    _name = 'biometric.attendance.report.wizard'
    _description = 'Rapport de présence'

    date_from = fields.Date(string='Du', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Au', required=True, default=fields.Date.context_today)
    employee_ids = fields.Many2many('hr.employee', string='Employés',
                                    help='Laissez vide pour tous les employés.')
    department_id = fields.Many2one('hr.department', string='Département')
    show_details = fields.Boolean(string='Détail jour par jour', default=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('La date de début doit précéder la date de fin.'))

    def _get_days(self):
        self.ensure_one()
        domain = [('date', '>=', self.date_from), ('date', '<=', self.date_to),
                  ('company_id', 'in', self.env.companies.ids)]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('department_id', 'child_of', self.department_id.id))
        return self.env['biometric.attendance.day'].search(domain, order='employee_id, date')

    def action_print(self):
        self.ensure_one()
        if not self._get_days():
            raise UserError(_('Aucune journée de présence sur cette période. '
                              'Lancez d’abord un recalcul si nécessaire.'))
        return self.env.ref(
            'primetech_biometric_attendance.action_report_biometric_attendance').report_action(self)

    def action_open_analysis(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.biometric_attendance_day_analysis_action')
        action['domain'] = [('id', 'in', self._get_days().ids)]
        return action
