from odoo import _, fields, models


class PrimetechMobileMoneyReportWizard(models.TransientModel):
    _name = "primetech.mobile.money.report.wizard"
    _description = "Rapport des transactions Mobile Money"

    date_from = fields.Date(string="Du", required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string="Au", required=True, default=fields.Date.today)
    provider = fields.Selection(
        [("all", "Tous les portefeuilles"), ("orange", "Orange Money"), ("momo", "MTN MoMo")],
        string="Portefeuille",
        required=True,
        default="all",
    )
    operation = fields.Selection(
        [("all", "Toutes les opérations"), ("withdrawal", "Retraits"), ("deposit", "Dépôts")],
        string="Opération",
        required=True,
        default="all",
    )
    employee_ids = fields.Many2many("hr.employee", string="Caissiers")
    wallet_ids = fields.Many2many(
        "pos.payment.method",
        string="Portefeuilles",
        domain="[('primetech_mobile_money_type', 'in', ('orange', 'momo'))]",
    )
    # Kept temporarily for already-open wizard views cached by the web
    # client.  The current form uses the multi-selection fields above.
    employee_id = fields.Many2one("hr.employee", string="Caissier (ancien)")
    payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Mode de paiement (ancien)",
    )

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            return self._raise_invalid_dates()
        domain = [
            ("primetech_mobile_money_provider", "!=", False),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.provider != "all":
            domain.append(("primetech_mobile_money_provider", "=", self.provider))
        if self.operation != "all":
            domain.append(("primetech_mobile_money_operation", "=", self.operation))
        if self.employee_ids:
            domain.append(("primetech_mobile_money_employee_id", "in", self.employee_ids.ids))
        if self.wallet_ids:
            domain.append(("primetech_mobile_money_payment_method_id", "in", self.wallet_ids.ids))
        transactions = self.env["account.bank.statement.line"].search(domain, order="date, id")
        deposits = sum(abs(line.amount) for line in transactions if line.primetech_mobile_money_operation == "deposit")
        withdrawals = sum(abs(line.amount) for line in transactions if line.primetech_mobile_money_operation == "withdrawal")
        return self.env.ref(
            "primetech_pos_hitech_theme.action_report_primetech_mobile_money_global"
        ).report_action(transactions, data={
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "employee": ", ".join(self.employee_ids.mapped("name")) or _("Tous les caissiers"),
            "wallet": ", ".join(self.wallet_ids.mapped("name")) or dict(self._fields["provider"].selection).get(self.provider),
            "operation": dict(self._fields["operation"].selection).get(self.operation),
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "total_count": len(transactions),
            "deposits": deposits,
            "withdrawals": withdrawals,
            "net": sum(transactions.mapped("amount")),
        })

    def _raise_invalid_dates(self):
        from odoo.exceptions import ValidationError
        raise ValidationError(_("La date de début doit être antérieure ou égale à la date de fin."))
