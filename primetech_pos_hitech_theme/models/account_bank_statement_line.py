from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    primetech_mobile_money_session_id = fields.Many2one(
        "pos.session",
        string="Session PDV Mobile Money",
        index=True,
        readonly=True,
        copy=False,
        help="Session à l'origine de ce mouvement Orange Money ou MTN MoMo.",
    )
    primetech_mobile_money_provider = fields.Selection(
        [("orange", "Orange Money"), ("momo", "MTN MoMo")],
        string="Portefeuille Mobile Money", readonly=True, copy=False, index=True,
    )
    primetech_mobile_money_operation = fields.Selection(
        [("withdrawal", "Retrait"), ("deposit", "Dépôt")],
        string="Type d'opération Mobile Money", readonly=True, copy=False, index=True,
    )
    primetech_mobile_money_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Mode de paiement Mobile Money",
        readonly=True,
        copy=False,
        index=True,
    )
    primetech_mobile_money_reason = fields.Char(
        string="Motif / numéro de téléphone",
        readonly=True,
        copy=False,
    )
