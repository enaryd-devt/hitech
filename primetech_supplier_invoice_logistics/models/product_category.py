# -*- coding: utf-8 -*-

from odoo import api, fields, models


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


class ProductTemplate(models.Model):
    _inherit = "product.template"

    weight = fields.Float(digits=(16, 6))
    volume = fields.Float(digits=(16, 6))
    primetech_supplier_invoice_history_ids = fields.Many2many(
        "account.move.line", compute="_compute_primetech_supplier_invoice_history",
        string="Historique factures fournisseurs", readonly=True, compute_sudo=True,
    )

    @api.depends("product_variant_ids")
    def _compute_primetech_supplier_invoice_history(self):
        invoice_lines = self.env["account.move.line"]
        for template in self:
            template.primetech_supplier_invoice_history_ids = invoice_lines.search([
                ("product_id.product_tmpl_id", "=", template.id),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")


class ProductProduct(models.Model):
    _inherit = "product.product"

    weight = fields.Float(digits=(16, 6))
    volume = fields.Float(digits=(16, 6))
    primetech_supplier_invoice_history_ids = fields.Many2many(
        "account.move.line", compute="_compute_primetech_supplier_invoice_history",
        string="Historique factures fournisseurs", readonly=True, compute_sudo=True,
    )

    def _compute_primetech_supplier_invoice_history(self):
        invoice_lines = self.env["account.move.line"]
        for product in self:
            product.primetech_supplier_invoice_history_ids = invoice_lines.search([
                ("product_id", "=", product.id),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")
