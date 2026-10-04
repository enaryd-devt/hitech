# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

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
