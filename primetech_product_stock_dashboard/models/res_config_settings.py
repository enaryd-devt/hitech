# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    primetech_default_alert_qty = fields.Float(
        string="Quantité d'alerte par défaut",
        config_parameter="primetech_product_stock_dashboard.default_alert_qty",
    )
    primetech_default_optimal_qty = fields.Float(
        string="Quantité optimale par défaut",
        config_parameter="primetech_product_stock_dashboard.default_optimal_qty",
    )

    def set_values(self):
        alert_qty = self.primetech_default_alert_qty
        optimal_qty = self.primetech_default_optimal_qty
        result = super().set_values()
        product_templates = self.env["product.template"].with_context(
            active_test=False,
            primetech_stock_global_update=True,
        )
        product_templates.search([
            ("is_storable", "=", True),
            ("primetech_stock_alert_qty_is_manual", "=", False),
        ]).write({"primetech_stock_alert_qty": alert_qty})
        product_templates.search([
            ("is_storable", "=", True),
            ("primetech_optimal_stock_qty_is_manual", "=", False),
        ]).write({"primetech_optimal_stock_qty": optimal_qty})
        return result
