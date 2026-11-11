# -*- coding: utf-8 -*-
from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    biometric_schedule_id = fields.Many2one(
        'biometric.attendance.schedule', string='Horaire de pointage',
        help="Horaire appliqué aux employés du département qui n'ont pas d'horaire propre "
             "(et aux sous-départements sans horaire).")
