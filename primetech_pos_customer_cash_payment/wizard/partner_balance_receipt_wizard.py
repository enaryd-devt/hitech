from odoo import _, api, fields, models


class PartnerBalanceReceiptWizard(models.TransientModel):
    _name = "primetech.partner.balance.receipt.wizard"
    _description = "Partner Balance Receipt"

    partner_id = fields.Many2one(
        "res.partner", string="Partenaire", required=True, domain=[("active", "=", True)]
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    balance_amount = fields.Monetary(
        string="Solde partenaire", compute="_compute_balance", currency_field="currency_id"
    )
    balance_direction = fields.Char(string="Situation", compute="_compute_balance")
    step = fields.Selection(
        [("selection", "Sélection"), ("preview", "Aperçu")],
        default="selection",
        required=True,
    )

    def _get_balance(self):
        self.ensure_one()
        commercial_partner = self.partner_id.commercial_partner_id
        lines = self.env["account.move.line"].search([
            ("partner_id", "child_of", commercial_partner.id),
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
        ])
        signed_balance = sum(lines.mapped("amount_residual"))
        if not signed_balance:
            direction = _("Solde réglé")
        else:
            direction = _("Le partenaire nous doit") if signed_balance > 0 else _("Nous devons au partenaire")
        return abs(signed_balance), direction

    @api.depends("partner_id", "company_id")
    def _compute_balance(self):
        for wizard in self:
            if wizard.partner_id:
                wizard.balance_amount, wizard.balance_direction = wizard._get_balance()
            else:
                wizard.balance_amount = 0
                wizard.balance_direction = False

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            "primetech_pos_customer_cash_payment.action_report_partner_balance_ticket"
        ).report_action(self)

    def _get_payment_receipt_proxy(self):
        """Build an in-memory payment rendered by the standard payment receipt."""
        self.ensure_one()
        partner_type = "supplier" if self.balance_direction == _("Nous devons au partenaire") else "customer"
        return self.env["account.payment"].with_context(
            partner_balance_receipt=True
        ).new({
            "name": _("Solde partenaire"),
            "partner_id": self.partner_id.id,
            "partner_type": partner_type,
            "payment_type": "outbound" if partner_type == "supplier" else "inbound",
            "amount": 0.0,
            "date": fields.Date.context_today(self),
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "create_uid": self.env.user.id,
            "memo": _("Situation globale client et fournisseur"),
        })

    def action_preview(self):
        self.ensure_one()
        self.step = "preview"
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form",
            "view_id": self.env.ref("primetech_pos_customer_cash_payment.view_partner_balance_receipt_wizard_form").id,
            "target": "new",
        }

    def action_back(self):
        self.ensure_one()
        self.step = "selection"
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form",
            "view_id": self.env.ref("primetech_pos_customer_cash_payment.view_partner_balance_receipt_wizard_form").id,
            "target": "new",
        }
