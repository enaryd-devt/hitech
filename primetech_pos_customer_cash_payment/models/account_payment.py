from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    pos_customer_cash_payment = fields.Boolean(
        string="Paiement client en espèces depuis le POS", copy=False, readonly=True
    )
    pos_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Mode de règlement POS",
        copy=False,
        readonly=True,
    )
    pos_manual_reconciliation = fields.Boolean(
        string="Lettrage manuel depuis le POS",
        copy=False,
        readonly=True,
    )
    pos_balance_before = fields.Monetary(
        string="Solde avant paiement", currency_field="currency_id", copy=False, readonly=True
    )
    pos_balance_after = fields.Monetary(
        string="Solde après paiement", currency_field="currency_id", copy=False, readonly=True
    )
