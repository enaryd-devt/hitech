# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    primetech_supplier_invoice_ids = fields.Many2many(
        "account.move", "primetech_invoice_receipt_rel", "picking_id", "move_id",
        string="Factures fournisseurs liées", readonly=True,
    )
    primetech_supplier_invoice_count = fields.Integer(
        compute="_compute_primetech_supplier_invoice_count", string="Factures fournisseurs",
    )

    def _compute_primetech_supplier_invoice_count(self):
        for picking in self:
            picking.primetech_supplier_invoice_count = len(picking.primetech_supplier_invoice_ids)

    def action_view_primetech_supplier_invoices(self):
        self.ensure_one()
        if len(self.primetech_supplier_invoice_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": self.primetech_supplier_invoice_ids.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
        action["domain"] = [("id", "in", self.primetech_supplier_invoice_ids.ids)]
        return action
