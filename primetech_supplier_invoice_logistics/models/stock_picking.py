# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        """A delivery created from an invoice can only leave after its validation."""
        for picking in self.filtered(lambda item: item.picking_type_code == "outgoing"):
            linked_invoices = picking.primetech_customer_invoice_ids.filtered(
                lambda move: move.move_type == "out_invoice"
            )
            if linked_invoices and any(invoice.state != "posted" for invoice in linked_invoices):
                raise UserError(_(
                    "La facture client liée doit être confirmée avant de valider ce bon de livraison."
                ))
        return super().button_validate()

    def _primetech_print_stock_document(self, expected_code, report_xmlid):
        self.ensure_one()
        if self.picking_type_code != expected_code:
            raise UserError(_("Ce document ne correspond pas au type de mouvement sélectionné."))
        return self.env.ref(report_xmlid).report_action(self)

    def action_print_primetech_receipt_note(self):
        return self._primetech_print_stock_document(
            "incoming", "primetech_supplier_invoice_logistics.action_report_primetech_receipt_note",
        )

    def action_print_primetech_delivery_note(self):
        return self._primetech_print_stock_document(
            "outgoing", "primetech_supplier_invoice_logistics.action_report_primetech_delivery_note",
        )

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
                # Force the invoice form, instead of the journal/action default view.
                "views": [(self.env.ref("account.view_move_form").id, "form")],
                "target": "current",
                "context": {"default_move_type": "out_invoice", "create": False},
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
