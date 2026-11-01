# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    primetech_supplier_invoice_id = fields.Many2one(
        "account.move", string="Facture fournisseur liée", copy=False,
        domain="[('move_type', '=', 'in_invoice')]",
    )

    primetech_partner_balance_after_payment = fields.Monetary(
        string="Solde partenaire après paiement",
        compute="_compute_primetech_partner_balance_after_payment",
        currency_field="currency_id",
    )
    primetech_partner_balance_message = fields.Char(
        string="Sens du solde partenaire",
        compute="_compute_primetech_partner_balance_after_payment",
    )

    @api.depends("partner_id", "payment_type")
    def _compute_primetech_partner_balance_after_payment(self):
        for payment in self:
            payment.primetech_partner_balance_after_payment = payment._primetech_partner_balance_after_payment()
            if payment.primetech_partner_balance_after_payment < 0:
                payment.primetech_partner_balance_message = "Le partenaire doit ce montant à l’entreprise"
            elif payment.primetech_partner_balance_after_payment > 0:
                payment.primetech_partner_balance_message = "L’entreprise doit ce montant au partenaire"
            else:
                payment.primetech_partner_balance_message = "Situation du partenaire soldée"

    def _primetech_partner_balance_after_payment(self):
        """Solde comptable du partenaire, après la comptabilisation du paiement."""
        self.ensure_one()
        if not self.partner_id:
            return 0.0
        # Convention du reçu client : négatif = dette du partenaire envers l'entreprise,
        # positif = dette de l'entreprise envers le partenaire.
        return self.partner_id.debit - self.partner_id.credit

    def _primetech_linked_document_references(self):
        self.ensure_one()
        return ", ".join(self.reconciled_invoice_ids.mapped("name")) or self.payment_reference or "—"

    def _primetech_receipt_payment_date(self):
        self.ensure_one()
        return fields.Date.to_date(self.date).strftime("%d-%m-%Y") if self.date else "—"

    def action_print_primetech_payment_receipt(self):
        self.ensure_one()
        return self.env.ref(
            "primetech_supplier_invoice_logistics.action_report_primetech_payment_receipt"
        ).report_action(self)

    def action_draft(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_(
                "Seul un administrateur Comptabilité peut remettre un paiement en brouillon."
            ))
        return super().action_draft()


class PrimetechSupplierAdvancePaymentWizard(models.TransientModel):
    _name = "primetech.supplier.advance.payment.wizard"
    _description = "Assistant d'acompte fournisseur"

    invoice_id = fields.Many2one("account.move", string="Facture fournisseur", required=True, readonly=True)
    partner_id = fields.Many2one(related="invoice_id.partner_id", readonly=True)
    currency_id = fields.Many2one(
        related="invoice_id.currency_id", string="Devise", readonly=True, store=True,
    )
    amount = fields.Monetary(string="Montant de l'acompte", required=True, currency_field="currency_id")
    payment_date = fields.Date(string="Date de paiement", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        "account.journal", string="Journal de paiement", required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(related="invoice_id.company_id", readonly=True)
    communication = fields.Char(string="Libellé")

    def action_create_payment(self):
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("Le montant de l'acompte doit être strictement positif."))
        if not self.journal_id:
            raise UserError(_("Veuillez sélectionner un journal de paiement avant de confirmer l'acompte."))
        method_line = self.journal_id.outbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(_("Configurez une méthode de paiement sortant sur le journal sélectionné."))
        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.partner_id.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "date": self.payment_date,
            "journal_id": self.journal_id.id,
            "payment_method_line_id": method_line.id,
            "payment_reference": self.communication,
            "primetech_supplier_invoice_id": self.invoice_id.id,
        })
        payment.action_post()
        return {"type": "ir.actions.act_window_close"}
