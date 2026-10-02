# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    primetech_supplier_invoice_ids = fields.Many2many(
        "account.move", "primetech_invoice_receipt_rel", "picking_id", "move_id",
        string="Factures fournisseurs liées", readonly=True,
    )
    primetech_supplier_invoice_count = fields.Integer(
        compute="_compute_primetech_supplier_invoice_count", string="Factures fournisseurs",
    )
    primetech_customer_invoice_ids = fields.Many2many(
        "account.move", "primetech_invoice_delivery_rel", "picking_id", "move_id",
        string="Factures clients liées", readonly=True,
    )
    primetech_customer_invoice_count = fields.Integer(
        compute="_compute_primetech_customer_invoice_count", string="Factures clients",
    )
    primetech_return_invoice_ids = fields.Many2many(
        "account.move", "primetech_invoice_return_rel", "picking_id", "move_id",
        string="Avoirs liés", readonly=True,
    )
    primetech_return_invoice_count = fields.Integer(
        compute="_compute_primetech_return_invoice_count", string="Avoirs",
    )

    def _compute_primetech_supplier_invoice_count(self):
        for picking in self:
            picking.primetech_supplier_invoice_count = len(picking.primetech_supplier_invoice_ids)

    def _compute_primetech_customer_invoice_count(self):
        for picking in self:
            picking.primetech_customer_invoice_count = len(picking.primetech_customer_invoice_ids)

    def _compute_primetech_return_invoice_count(self):
        for picking in self:
            picking.primetech_return_invoice_count = len(picking.primetech_return_invoice_ids)

    def unlink(self):
        if self.filtered(lambda picking: (
            picking.primetech_supplier_invoice_ids
            or picking.primetech_customer_invoice_ids
            or picking.primetech_return_invoice_ids
        )):
            raise UserError(_("Ce mouvement est lié à une facture ou un avoir et ne peut pas être supprimé."))
        return super().unlink()

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

    def action_view_primetech_customer_invoices(self):
        self.ensure_one()
        if len(self.primetech_customer_invoice_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": self.primetech_customer_invoice_ids.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action["domain"] = [("id", "in", self.primetech_customer_invoice_ids.ids)]
        return action

    def action_view_primetech_return_invoices(self):
        self.ensure_one()
        if len(self.primetech_return_invoice_ids) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": self.primetech_return_invoice_ids.id, "view_mode": "form",
                "views": [(False, "form")], "target": "current",
            }
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_refund_type")
        action["domain"] = [("id", "in", self.primetech_return_invoice_ids.ids)]
        return action
