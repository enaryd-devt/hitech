# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    biometric_default_schedule_id = fields.Many2one(
        related='company_id.biometric_default_schedule_id', readonly=False)
    biometric_use_resource_calendar = fields.Boolean(
        related='company_id.biometric_use_resource_calendar', readonly=False)
    biometric_punch_mode = fields.Selection(
        related='company_id.biometric_punch_mode', readonly=False)
    biometric_min_punch_interval = fields.Integer(
        related='company_id.biometric_min_punch_interval', readonly=False)
    biometric_generate_attendance = fields.Boolean(
        related='company_id.biometric_generate_attendance', readonly=False)
    biometric_log_retention_days = fields.Integer(
        related='company_id.biometric_log_retention_days', readonly=False)
