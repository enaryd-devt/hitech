# -*- coding: utf-8 -*-
from odoo import fields, models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    replenishment_request_id = fields.Many2one("replenishment.request", index=True, copy=False)
