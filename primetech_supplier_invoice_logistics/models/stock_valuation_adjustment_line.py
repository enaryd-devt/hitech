from odoo import api, fields, models


class StockValuationAdjustmentLine(models.Model):
    _inherit = "stock.valuation.adjustment.lines"

    primetech_unit_landed_cost = fields.Monetary(
        string="Coût unitaire réparti",
        compute="_compute_primetech_unit_landed_cost",
        currency_field="currency_id",
        readonly=True,
    )

    @api.depends("additional_landed_cost", "quantity")
    def _compute_primetech_unit_landed_cost(self):
        for line in self:
            line.primetech_unit_landed_cost = (
                (line.additional_landed_cost or 0.0) / line.quantity
                if line.quantity else 0.0
            )
