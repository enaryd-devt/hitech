# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BiometricAttendanceRecomputeWizard(models.TransientModel):
    _name = 'biometric.attendance.recompute.wizard'
    _description = 'Recalcul des journées de présence'

    date_from = fields.Date(string='Du', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Au', required=True, default=fields.Date.context_today)
    employee_ids = fields.Many2many('hr.employee', string='Employés',
                                    help='Laissez vide pour tous les employés suivis.')
    department_id = fields.Many2one('hr.department', string='Département')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('La date de début doit précéder la date de fin.'))
            if (wizard.date_to - wizard.date_from) > timedelta(days=366):
                raise UserError(_('La période ne peut pas dépasser un an.'))

    def action_recompute(self):
        self.ensure_one()
        employees = None
        if self.employee_ids or self.department_id:
            employees = self.employee_ids
            if self.department_id:
                employees |= self.env['hr.employee'].search([
                    ('department_id', 'child_of', self.department_id.id)])
        count = self.env['biometric.attendance.day']._recompute_period(
            self.date_from, min(self.date_to, fields.Date.context_today(self)), employees)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Analyse terminée'),
                'message': _('%s journée(s) employé analysée(s).', count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
