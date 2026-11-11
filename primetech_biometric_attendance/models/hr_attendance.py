# -*- coding: utf-8 -*-
from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    in_mode = fields.Selection(
        selection_add=[('biometric', 'Pointeuse biométrique')],
        ondelete={'biometric': 'set default'})
    out_mode = fields.Selection(
        selection_add=[('biometric', 'Pointeuse biométrique')],
        ondelete={'biometric': 'set default'})
    biometric_day_id = fields.Many2one(
        'biometric.attendance.day', string='Journée de pointage', index='btree_not_null',
        ondelete='set null', readonly=True, copy=False,
        help="Présence générée automatiquement à partir des pointages biométriques.")
