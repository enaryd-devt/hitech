from datetime import datetime

from odoo import models


class SalesPeriodicXlsx(models.AbstractModel):
    _name = "report.primetech_reporting_center.sales_periodic_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Rapport XLSX Périodique des Ventes"

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env["primetech.sales.periodic.report"].get_report_data(
            date_from=wizard.date_from, date_to=wizard.date_to,
            company_id=wizard.company_id.id,
            user_id=wizard.user_id.id if wizard.user_id else False,
            partner_id=wizard.partner_id.id if wizard.partner_id else False,
            warehouse_ids=wizard.warehouse_ids.ids, state_filter=wizard.state_filter,
        )
        sheet = workbook.add_worksheet("Rapport Ventes")
        title = workbook.add_format({"bold": True, "font_size": 16, "align": "center", "valign": "vcenter", "border": 1, "bg_color": "#0F4C5C", "font_color": "#FFFFFF"})
        section = workbook.add_format({"bold": True, "border": 1, "bg_color": "#0F4C5C", "font_color": "#FFFFFF"})
        header = workbook.add_format({"bold": True, "border": 1, "align": "center", "bg_color": "#1B7F8C", "font_color": "#FFFFFF"})
        cell = workbook.add_format({"border": 1})
        number = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        money = workbook.add_format({"border": 1, "num_format": "#,##0"})
        percent = workbook.add_format({"border": 1, "num_format": "0.0%"})
        total = workbook.add_format({"bold": True, "border": 1, "bg_color": "#EEF7F8"})
        total_money = workbook.add_format({"bold": True, "border": 1, "bg_color": "#EEF7F8", "num_format": "#,##0"})
        total_number = workbook.add_format({"bold": True, "border": 1, "bg_color": "#EEF7F8", "num_format": "#,##0.00"})

        def heading(row, label, columns):
            sheet.merge_range(row, 0, row, columns - 1, label, section)
            return row + 1

        def table(row, columns, rows, formats=None):
            for col, label in enumerate(columns):
                sheet.write(row, col, label, header)
            for values in rows:
                row += 1
                for col, value in enumerate(values):
                    sheet.write(row, col, value, (formats or [cell] * len(columns))[col])
            return row + 1

        summary = report_data["summary"]
        row = 0
        sheet.merge_range(row, 0, row, 10, "RAPPORT PÉRIODIQUE DES VENTES", title)
        row += 2
        sheet.write(row, 0, "Période : %s au %s" % (wizard.date_from, wizard.date_to))
        sheet.write(row, 7, "Imprimé le : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        row += 2

        row = heading(row, "SYNTHÈSE PAR ARTICLE — STOCK À LA FIN DE PÉRIODE", 7)
        sheet.merge_range(row, 0, row, 6, "Entrepôt(s) d'étude : " + (", ".join(report_data["warehouse_names"]) or "Tous les entrepôts de la société"), cell)
        row += 1
        product_rows = [[item["product"], item["qty"], item.get("stock_remaining", 0.0), item["ht"], item.get("cost", 0.0), item.get("margin", 0.0), item.get("margin_rate", 0.0) / 100] for item in report_data["product_summary"]]
        row = table(row, ["Article", "Quantité vendue", "Stock restant", "CA HT", "Coût", "Marge HT", "Taux"], product_rows, [cell, number, number, money, money, money, percent])
        for col, value in enumerate(["Total", "", "", summary["turnover_ht"], summary["cost"], summary["margin"], summary["margin_rate"] / 100]):
            sheet.write(row, col, value, [total, total, total, total_money, total_money, total_money, percent][col])
        row += 2

        row = heading(row, "DÉTAIL DES VENTES", 11)
        sales_rows = [[item["invoice"], str(item["date"]), item["customer"], item["seller"], item["product"], item["qty"], item["unit_price"], item["ht"], item["ttc"], item.get("margin", 0.0), item.get("margin_rate", 0.0) / 100] for item in report_data["sales_lines"]]
        row = table(row, ["Facture", "Date", "Client", "Vendeur", "Article", "Qté", "PU HT", "Total HT", "Total TTC", "Marge HT", "Taux"], sales_rows, [cell, cell, cell, cell, cell, number, money, money, money, money, percent]) + 1

        row = heading(row, "RÉSUMÉ GÉNÉRAL", 2)
        for label, value, fmt in [("Nombre de factures", summary["invoice_count"], cell), ("Nombre de clients", summary["customer_count"], cell), ("Nombre de vendeurs", summary["seller_count"], cell), ("Chiffre d'Affaire Hors Taxes", summary["turnover_ht"], money), ("Chiffre d'Affaire TTC", summary["turnover_ttc"], money), ("Coût des ventes", summary["cost"], money), ("Marge brute HT", summary["margin"], money), ("Taux de marge", summary["margin_rate"] / 100, percent)]:
            sheet.write(row, 0, label, cell)
            sheet.write(row, 1, value, fmt)
            row += 1
        row += 1

        row = heading(row, "SYNTHÈSE PAR VENDEUR", 6)
        seller_rows = [[item["seller"], item["qty"], item["ht"], item["ttc"], item.get("margin", 0.0), item.get("margin_rate", 0.0) / 100] for item in report_data["seller_summary"]]
        row = table(row, ["Vendeur", "Quantité vendue", "CA HT", "CA TTC", "Marge HT", "Taux"], seller_rows, [cell, number, money, money, money, percent]) + 1

        row = heading(row, "SYNTHÈSE PAR CLIENT", 5)
        customer_rows = [[item["customer"], item["ht"], item["ttc"], item.get("margin", 0.0), item.get("margin_rate", 0.0) / 100] for item in report_data["customer_summary"]]
        table(row, ["Client", "CA HT", "CA TTC", "Marge HT", "Taux"], customer_rows, [cell, money, money, money, percent])
        sheet.freeze_panes(4, 0)
        sheet.set_column("A:A", 20)
        sheet.set_column("B:B", 14)
        sheet.set_column("C:D", 24)
        sheet.set_column("E:E", 34)
        sheet.set_column("F:F", 14)
        sheet.set_column("G:K", 16)
