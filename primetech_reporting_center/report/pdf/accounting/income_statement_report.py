from odoo import fields, models


class IncomeStatementReport(models.AbstractModel):
    _name = "report.primetech_reporting_center.income_statement_template"
    _description = "Compte de Résultat OHADA Report"

    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard = self.env["primetech.income.statement.wizard"].browse(docids[:1])
        date_from = fields.Date.to_date(data.get("date_from") or wizard.date_from)
        date_to = fields.Date.to_date(data.get("date_to") or wizard.date_to)
        posted_only = data.get("posted_only") if "posted_only" in data else wizard.posted_only
        report_data = self.env["primetech.income.statement"].get_income_statement(
            date_from=date_from,
            date_to=date_to,
            posted_only=posted_only,
        )
        return {
            "docs": wizard,
            "data": report_data,
            "date_from": date_from,
            "date_to": date_to,
            "generated_at": fields.Datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
