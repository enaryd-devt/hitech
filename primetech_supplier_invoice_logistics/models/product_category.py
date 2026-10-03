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
    primetech_customer_invoice_history_ids = fields.Many2many(
        "account.move.line", compute="_compute_primetech_supplier_invoice_history",
        string="Historique factures clients", readonly=True, compute_sudo=True,
    )
    primetech_history_currency_id = fields.Many2one(
        "res.currency", compute="_compute_primetech_supplier_invoice_history",
        string="Devise des totaux", readonly=True,
    )
    primetech_purchase_invoice_qty = fields.Float(
        compute="_compute_primetech_supplier_invoice_history", string="Qté achetée", readonly=True,
    )
    primetech_purchase_invoice_received_qty = fields.Float(
        compute="_compute_primetech_supplier_invoice_history", string="Qté reçue", readonly=True,
    )
    primetech_purchase_invoice_total = fields.Monetary(
        compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id",
        string="Total achats", readonly=True,
    )
    primetech_sale_invoice_qty = fields.Float(
        compute="_compute_primetech_supplier_invoice_history", string="Qté vendue", readonly=True,
    )
    primetech_sale_invoice_delivered_qty = fields.Float(
        compute="_compute_primetech_supplier_invoice_history", string="Qté livrée", readonly=True,
    )
    primetech_sale_invoice_total = fields.Monetary(
        compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id",
        string="Total ventes", readonly=True,
    )
    primetech_pos_sale_history_ids = fields.Many2many(
        "primetech.product.sale.history", compute="_compute_primetech_supplier_invoice_history",
        string="Historique ventes PdV", readonly=True, compute_sudo=True,
    )
    primetech_pos_sale_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté PdV", readonly=True)
    primetech_pos_sale_total = fields.Monetary(
        compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id",
        string="Total PdV", readonly=True,
    )
    primetech_total_sales_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté totale vendue", readonly=True)

    @api.depends("product_variant_ids")
    def _compute_primetech_supplier_invoice_history(self):
        invoice_lines = self.env["account.move.line"]
        for template in self:
            supplier_lines = invoice_lines.search([
                ("product_id.product_tmpl_id", "=", template.id),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")
            customer_lines = invoice_lines.search([
                ("product_id.product_tmpl_id", "=", template.id),
                ("move_id.move_type", "=", "out_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")
            template.primetech_supplier_invoice_history_ids = supplier_lines
            template.primetech_customer_invoice_history_ids = customer_lines
            template.primetech_history_currency_id = template.company_id.currency_id or self.env.company.currency_id
            template.primetech_purchase_invoice_qty = sum(supplier_lines.mapped("quantity"))
            template.primetech_purchase_invoice_received_qty = sum(supplier_lines.mapped("primetech_quantity_received"))
            template.primetech_purchase_invoice_total = sum(abs(line.balance) for line in supplier_lines)
            template.primetech_sale_invoice_qty = sum(customer_lines.mapped("quantity"))
            template.primetech_sale_invoice_delivered_qty = sum(customer_lines.mapped("primetech_quantity_delivered"))
            template.primetech_sale_invoice_total = sum(abs(line.balance) for line in customer_lines)
            pos_history = self.env["primetech.product.sale.history"].search([
                ("product_tmpl_id", "=", template.id), ("source", "=", "pos"),
            ])
            template.primetech_pos_sale_history_ids = pos_history
            template.primetech_pos_sale_qty = sum(pos_history.mapped("quantity"))
            template.primetech_pos_sale_total = sum(pos_history.mapped("subtotal"))
            template.primetech_total_sales_qty = template.primetech_sale_invoice_qty + template.primetech_pos_sale_qty

    def _primetech_open_invoice_history(self, history_field, title):
        self.ensure_one()
        history_lines = self[history_field]
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("primetech_supplier_invoice_logistics.view_primetech_product_invoice_history_list").id, "list"), (False, "form")],
            "domain": [("id", "in", history_lines.ids)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_open_primetech_sale_invoice_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": "Historique des ventes",
            "res_model": "primetech.product.sale.history", "view_mode": "list,form",
            "views": [(self.env.ref("primetech_supplier_invoice_logistics.view_primetech_product_sale_history_list").id, "list"), (False, "form")],
            "domain": [("product_tmpl_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_open_primetech_purchase_invoice_history(self):
        return self._primetech_open_invoice_history("primetech_supplier_invoice_history_ids", "Historique des achats")


class ProductProduct(models.Model):
    _inherit = "product.product"

    weight = fields.Float(digits=(16, 6))
    volume = fields.Float(digits=(16, 6))
    primetech_supplier_invoice_history_ids = fields.Many2many(
        "account.move.line", compute="_compute_primetech_supplier_invoice_history",
        string="Historique factures fournisseurs", readonly=True, compute_sudo=True,
    )
    primetech_customer_invoice_history_ids = fields.Many2many(
        "account.move.line", compute="_compute_primetech_supplier_invoice_history",
        string="Historique factures clients", readonly=True, compute_sudo=True,
    )
    primetech_history_currency_id = fields.Many2one(
        "res.currency", compute="_compute_primetech_supplier_invoice_history",
        string="Devise des totaux", readonly=True,
    )
    primetech_purchase_invoice_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté achetée", readonly=True)
    primetech_purchase_invoice_received_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté reçue", readonly=True)
    primetech_purchase_invoice_total = fields.Monetary(compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id", string="Total achats", readonly=True)
    primetech_sale_invoice_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté vendue", readonly=True)
    primetech_sale_invoice_delivered_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté livrée", readonly=True)
    primetech_sale_invoice_total = fields.Monetary(compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id", string="Total ventes", readonly=True)
    primetech_pos_sale_history_ids = fields.Many2many("primetech.product.sale.history", compute="_compute_primetech_supplier_invoice_history", string="Historique ventes PdV", readonly=True, compute_sudo=True)
    primetech_pos_sale_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté PdV", readonly=True)
    primetech_pos_sale_total = fields.Monetary(compute="_compute_primetech_supplier_invoice_history", currency_field="primetech_history_currency_id", string="Total PdV", readonly=True)
    primetech_total_sales_qty = fields.Float(compute="_compute_primetech_supplier_invoice_history", string="Qté totale vendue", readonly=True)

    def _compute_primetech_supplier_invoice_history(self):
        invoice_lines = self.env["account.move.line"]
        for product in self:
            supplier_lines = invoice_lines.search([
                ("product_id", "=", product.id),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")
            customer_lines = invoice_lines.search([
                ("product_id", "=", product.id),
                ("move_id.move_type", "=", "out_invoice"),
                ("move_id.state", "=", "posted"),
            ], order="date desc, id desc")
            product.primetech_supplier_invoice_history_ids = supplier_lines
            product.primetech_customer_invoice_history_ids = customer_lines
            product.primetech_history_currency_id = product.company_id.currency_id or self.env.company.currency_id
            product.primetech_purchase_invoice_qty = sum(supplier_lines.mapped("quantity"))
            product.primetech_purchase_invoice_received_qty = sum(supplier_lines.mapped("primetech_quantity_received"))
            product.primetech_purchase_invoice_total = sum(abs(line.balance) for line in supplier_lines)
            product.primetech_sale_invoice_qty = sum(customer_lines.mapped("quantity"))
            product.primetech_sale_invoice_delivered_qty = sum(customer_lines.mapped("primetech_quantity_delivered"))
            product.primetech_sale_invoice_total = sum(abs(line.balance) for line in customer_lines)
            pos_history = self.env["primetech.product.sale.history"].search([
                ("product_id", "=", product.id), ("source", "=", "pos"),
            ])
            product.primetech_pos_sale_history_ids = pos_history
            product.primetech_pos_sale_qty = sum(pos_history.mapped("quantity"))
            product.primetech_pos_sale_total = sum(pos_history.mapped("subtotal"))
            product.primetech_total_sales_qty = product.primetech_sale_invoice_qty + product.primetech_pos_sale_qty

    def _primetech_open_invoice_history(self, history_field, title):
        self.ensure_one()
        history_lines = self[history_field]
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("primetech_supplier_invoice_logistics.view_primetech_product_invoice_history_list").id, "list"), (False, "form")],
            "domain": [("id", "in", history_lines.ids)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_open_primetech_sale_invoice_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": "Historique des ventes",
            "res_model": "primetech.product.sale.history", "view_mode": "list,form",
            "views": [(self.env.ref("primetech_supplier_invoice_logistics.view_primetech_product_sale_history_list").id, "list"), (False, "form")],
            "domain": [("product_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_open_primetech_purchase_invoice_history(self):
        return self._primetech_open_invoice_history("primetech_supplier_invoice_history_ids", "Historique des achats")
