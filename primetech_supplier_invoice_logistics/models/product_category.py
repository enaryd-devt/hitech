# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    primetech_cost_percentage = fields.Float(string="Pourcentage de revient", default=0.0)
    primetech_sale_percentage = fields.Float(string="Pourcentage vente", default=0.0)
    primetech_rank = fields.Selection(
        [
            ("family", "Famille"),
            ("large_family", "Grande Famille"),
            ("sub_family", "Sous Famille"),
        ],
        string="Rang", default="family",
    )
    primetech_reference = fields.Char(string="Référence")
