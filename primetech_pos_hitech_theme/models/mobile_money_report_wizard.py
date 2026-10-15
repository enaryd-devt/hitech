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
        transactions = self.env["account.bank.statement.line"].search(domain, order="date, id")
        return self.env.ref(
            "primetech_pos_hitech_theme.action_report_primetech_mobile_money_global"
        ).report_action(transactions, data={
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        })

    def _raise_invalid_dates(self):
        from odoo.exceptions import ValidationError
        raise ValidationError(_("La date de début doit être antérieure ou égale à la date de fin."))
