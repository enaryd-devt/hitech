# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    replenishment_request_id = fields.Many2one("replenishment.request", index=True, copy=False)

    def _action_done(self):
        result = super()._action_done()
        self.mapped("replenishment_request_id")._create_transfer_cost_valuation_layers()
        return result
