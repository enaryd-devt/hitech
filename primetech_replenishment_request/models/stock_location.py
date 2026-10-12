# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"


class ResUsers(models.Model):
    _inherit = "res.users"

    replenishment_warehouse_ids = fields.Many2many(
        "stock.warehouse", "replenishment_user_warehouse_rel", "user_id", "warehouse_id",
        string="Entrepôts de réapprovisionnement autorisés",
    )
