from odoo import _, fields, models


class PrimetechMobileMoneyGlobalReport(models.AbstractModel):
    _name = "report.primetech_pos_hitech_theme.mobile_money_global"
    _description = "Rapport global Mobile Money"

    def _get_report_values(self, docids, data=None):
        """Always provide report data, including direct POS print calls."""
        statement_line = self.env["account.bank.statement.line"]
        docs = statement_line.browse(docids).exists() if docids else statement_line.browse()
        if not docs:
            docs = statement_line.search(
                [("primetech_mobile_money_provider", "!=", False)],
                order="date, id",
            )
        data = dict(data or {})
        dates = docs.mapped("date")
        date_from = min(dates) if dates else fields.Date.context_today(self)
        date_to = max(dates) if dates else fields.Date.context_today(self)
        deposits = sum(abs(line.amount) for line in docs if line.primetech_mobile_money_operation == "deposit")
        withdrawals = sum(abs(line.amount) for line in docs if line.primetech_mobile_money_operation == "withdrawal")
        data.setdefault("date_from", fields.Date.to_string(date_from))
        data.setdefault("date_to", fields.Date.to_string(date_to))
        data.setdefault("employee", _("Tous les caissiers"))
        data.setdefault("wallet", _("Tous les portefeuilles"))
        data.setdefault("operation", _("Toutes les opérations"))
        data.setdefault("generated_at", fields.Datetime.to_string(fields.Datetime.now()))
        data.setdefault("total_count", len(docs))
        data.setdefault("deposits", deposits)
        data.setdefault("withdrawals", withdrawals)
        data.setdefault("net", sum(docs.mapped("amount")))
        return {
            "doc_ids": docs.ids,
            "doc_model": "account.bank.statement.line",
            "docs": docs,
            "data": data,
        }
