# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PrimeTechReportingSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    primetech_stock_min_alert_threshold = fields.Float(
        string="Seuil d'alerte produit",
        default=10.0,
        config_parameter='primetech_reporting_center.stock_min_alert_threshold',
    )
    primetech_stock_overstock_threshold = fields.Float(
        string='Seuil maximal de surstock',
        default=2000.0,
        config_parameter='primetech_reporting_center.stock_overstock_threshold',
    )
    primetech_theme_primary_color = fields.Char(
        string='Couleur principale',
        default='#0F6CBD',
        config_parameter='primetech_reporting_center.theme_primary_color',
    )
    primetech_theme_kpi_style = fields.Selection(
        [('cards', 'Cartes'), ('compact', 'Compact'), ('outlined', 'Contour')],
        string='Style des KPI',
        default='cards',
        config_parameter='primetech_reporting_center.theme_kpi_style',
    )
    primetech_theme_chart_format = fields.Selection(
        [('line', 'Courbes'), ('bar', 'Barres'), ('doughnut', 'Anneaux')],
        string='Format des graphiques',
        default='line',
        config_parameter='primetech_reporting_center.theme_chart_format',
    )


class PrimeTechReportingSettingsService(models.AbstractModel):
    _name = 'primetech.reporting.settings'
    _description = 'Paramètres PrimeTech Reporting Center'

    @api.model
    def _get_float_param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        try:
            return float(value) if value not in (None, '') else default
        except (TypeError, ValueError):
            return default

    @api.model
    def get_values(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'stock_min_alert_threshold': self._get_float_param('primetech_reporting_center.stock_min_alert_threshold', 10.0),
            'stock_overstock_threshold': self._get_float_param('primetech_reporting_center.stock_overstock_threshold', 2000.0),
            'theme_primary_color': params.get_param('primetech_reporting_center.theme_primary_color') or '#0F6CBD',
            'theme_kpi_style': params.get_param('primetech_reporting_center.theme_kpi_style') or 'cards',
            'theme_chart_format': params.get_param('primetech_reporting_center.theme_chart_format') or 'line',
        }
