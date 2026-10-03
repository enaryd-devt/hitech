# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _default_primetech_stock_alert_qty(self):
        return float(self.env["ir.config_parameter"].sudo().get_param(
            "primetech_product_stock_dashboard.default_alert_qty", "0"
        ))

    @api.model
    def _default_primetech_optimal_stock_qty(self):
        return float(self.env["ir.config_parameter"].sudo().get_param(
            "primetech_product_stock_dashboard.default_optimal_qty", "0"
        ))

    primetech_stock_alert_qty = fields.Float(
        string="Quantité d'alerte",
        default=_default_primetech_stock_alert_qty,
        help="Le stock est affiché en alerte lorsque la quantité disponible atteint ce seuil.",
    )
    primetech_optimal_stock_qty = fields.Float(
        string="Quantité optimale",
        default=_default_primetech_optimal_stock_qty,
        help="Niveau de stock cible utilisé par les jauges du tableau Kanban.",
    )
    primetech_stock_alert_qty_is_manual = fields.Boolean(default=False, copy=False)
    primetech_optimal_stock_qty_is_manual = fields.Boolean(default=False, copy=False)
    primetech_stock_level = fields.Selection(
        [("critical", "Critique"), ("warning", "À surveiller"), ("healthy", "Satisfaisant")],
        string="Niveau de stock",
        compute="_compute_primetech_stock_indicators",
    )
    primetech_stock_ratio = fields.Float(
        string="Taux de stock",
        compute="_compute_primetech_stock_indicators",
    )
    primetech_forecast_ratio = fields.Float(
        string="Taux de stock prévu",
        compute="_compute_primetech_stock_indicators",
    )

    def write(self, vals):
        """Keep track of thresholds intentionally adjusted on an article.

        Global settings only update articles that still use the default values.
        The context flag is used exclusively by the settings propagation.
        """
        if not self.env.context.get("primetech_stock_global_update"):
            vals = dict(vals)
            if "primetech_stock_alert_qty" in vals:
                vals["primetech_stock_alert_qty_is_manual"] = True
            if "primetech_optimal_stock_qty" in vals:
                vals["primetech_optimal_stock_qty_is_manual"] = True
        return super().write(vals)

    @api.depends(
        "is_storable",
        "qty_available",
        "virtual_available",
        "primetech_stock_alert_qty",
        "primetech_optimal_stock_qty",
    )
    def _compute_primetech_stock_indicators(self):
        for product in self:
            # Services and consumables that do not track inventory must never
            # be classified as low stock simply because their quantity is 0.
            if not product.is_storable:
                product.primetech_stock_level = False
                product.primetech_stock_ratio = 0.0
                product.primetech_forecast_ratio = 0.0
                continue
            available = product.qty_available or 0.0
            optimal = product.primetech_optimal_stock_qty or 0.0
            alert = product.primetech_stock_alert_qty or 0.0
            if available <= 0:
                product.primetech_stock_level = "critical"
            elif available <= alert:
                product.primetech_stock_level = "warning"
            else:
                product.primetech_stock_level = "healthy"
            product.primetech_stock_ratio = min(max((available / optimal * 100.0) if optimal else 0.0, 0.0), 100.0)
            forecast = product.virtual_available or 0.0
            product.primetech_forecast_ratio = min(max((forecast / optimal * 100.0) if optimal else 0.0, 0.0), 100.0)
