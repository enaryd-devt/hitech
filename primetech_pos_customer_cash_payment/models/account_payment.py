from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.depends("reconciled_invoice_ids.payment_state", "move_id.line_ids.amount_residual")
    def _compute_state(self):
        """Reflect a completed manual partner reconciliation on POS payments.

        The POS cash statement can remain open until the cash closing.  Its
        technical liquidity line would normally keep the payment in process,
        although the partner debt/credit has already been manually matched.
        For a POS payment explicitly left for manual reconciliation, its state
        must become paid as soon as its partner counterpart is reconciled.
        """
        super()._compute_state()
        for payment in self.filtered(
            lambda payment: payment.pos_customer_cash_payment
            and payment.pos_manual_reconciliation
            and payment.state in ("in_process", "paid")
        ):
            _liquidity_lines, counterpart_lines, _writeoff_lines = payment._seek_for_lines()
            if counterpart_lines and all(counterpart_lines.mapped("reconciled")):
                payment.state = "paid"

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
