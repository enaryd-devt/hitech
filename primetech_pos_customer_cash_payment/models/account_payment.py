from odoo import _, api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _compute_payment_receipt_title(self):
        super()._compute_payment_receipt_title()
        if self.env.context.get("partner_balance_receipt"):
            self.payment_receipt_title = _("Reçu de solde partenaire")

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
    pos_balance_before_direction = fields.Selection(
        [
            ("partner_owes", "Le partenaire nous doit"),
            ("customer_owes", "Customer owes company"),
            ("company_owes", "Company owes partner"),
            ("supplier_owes", "Supplier owes company"),
            ("settled", "Settled"),
        ],
        string="Balance situation before payment",
        copy=False,
        readonly=True,
    )
    pos_balance_after_direction = fields.Selection(
        [
            ("partner_owes", "Le partenaire nous doit"),
            ("customer_owes", "Customer owes company"),
            ("company_owes", "Company owes partner"),
            ("supplier_owes", "Supplier owes company"),
            ("settled", "Settled"),
        ],
        string="Balance situation after payment",
        copy=False,
        readonly=True,
    )
    receipt_balance_snapshot_before = fields.Monetary(
        string="Receipt balance before", currency_field="currency_id", copy=False, readonly=True
    )
    receipt_balance_snapshot_after = fields.Monetary(
        string="Receipt balance at date", currency_field="currency_id", copy=False, readonly=True
    )
    receipt_balance_snapshot_before_label = fields.Char(copy=False, readonly=True)
    receipt_balance_snapshot_after_label = fields.Char(copy=False, readonly=True)
    receipt_balance_snapshot_date = fields.Datetime(copy=False, readonly=True)

    def _pos_balance_direction_label(self, direction):
        """Return the receipt wording of an unsigned accounting balance."""
        self.ensure_one()
        return {
            "partner_owes": _("Le partenaire nous doit"),
            "customer_owes": _("Client nous doit"),
            "company_owes": _("Nous devons au partenaire"),
            "supplier_owes": _("Fournisseur nous doit"),
            "settled": _("Solde réglé"),
        }.get(direction, "")

    def _get_partner_receipt_balance_values(self):
        """Return unsigned before/after balances for the A4 payment receipt."""
        self.ensure_one()
        if not self.partner_id or self.partner_type not in ("customer", "supplier"):
            return {"before_amount": 0.0, "after_amount": 0.0, "before_label": "", "after_label": ""}
        if self.receipt_balance_snapshot_date and not self.env.context.get("partner_balance_receipt"):
            return {
                "before_amount": self.receipt_balance_snapshot_before,
                "after_amount": self.receipt_balance_snapshot_after,
                "before_label": self.receipt_balance_snapshot_before_label,
                "after_label": self.receipt_balance_snapshot_after_label,
            }
        lines = self.env["account.move.line"].search([
            ("partner_id", "child_of", self.partner_id.commercial_partner_id.id),
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
        ])
        after_signed = sum(lines.mapped("amount_residual"))
        payment_line = self.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
            and line.partner_id.commercial_partner_id == self.partner_id.commercial_partner_id
        )[:1]
        before_signed = after_signed - (payment_line.balance if payment_line else 0.0)

        def label(value):
            if not value:
                return _("Solde réglé")
            return _("Le partenaire nous doit") if value > 0 else _("Nous devons au partenaire")

        values = {
            "before_amount": abs(before_signed),
            "after_amount": abs(after_signed),
            "before_label": label(before_signed),
            "after_label": label(after_signed),
        }
        # A receipt is legal evidence: retain the balance shown at its first
        # printing date instead of recalculating it on later reprints.
        if self.id and not self.env.context.get("partner_balance_receipt"):
            self.sudo().write({
                "receipt_balance_snapshot_before": values["before_amount"],
                "receipt_balance_snapshot_after": values["after_amount"],
                "receipt_balance_snapshot_before_label": values["before_label"],
                "receipt_balance_snapshot_after_label": values["after_label"],
                "receipt_balance_snapshot_date": fields.Datetime.now(),
            })
        return values
