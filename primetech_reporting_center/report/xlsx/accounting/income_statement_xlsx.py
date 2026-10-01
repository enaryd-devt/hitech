from odoo import models


class IncomeStatementXlsx(models.AbstractModel):
    _name = "report.primetech_reporting_center.income_statement_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Compte de Résultat OHADA XLSX"

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env["primetech.income.statement"].get_income_statement(
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            posted_only=data.get("posted_only", True),
        )
        sheet = workbook.add_worksheet("Compte résultat OHADA")
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.hide_gridlines(2)
        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 52)
        sheet.set_column("C:C", 6)
        sheet.set_column("D:D", 8)
        sheet.set_column("E:E", 9)
        sheet.set_column("F:G", 18)

        title = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#FFFFFF", "bg_color": "#1B366A", "align": "center", "valign": "vcenter"})
        subtitle = workbook.add_format({"italic": True, "font_color": "#52657E", "align": "center"})
        header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1B366A", "align": "center", "valign": "vcenter", "border": 1})
        text = workbook.add_format({"border": 1, "border_color": "#B8C5D8"})
        centered = workbook.add_format({"border": 1, "border_color": "#B8C5D8", "align": "center"})
        amount = workbook.add_format({"border": 1, "border_color": "#B8C5D8", "num_format": "#,##0;[Red]-#,##0", "align": "right"})
        subtotal_text = workbook.add_format({"bold": True, "bg_color": "#E8EEF8", "border": 1, "border_color": "#B8C5D8"})
        subtotal_centered = workbook.add_format({"bold": True, "bg_color": "#E8EEF8", "border": 1, "border_color": "#B8C5D8", "align": "center"})
        subtotal_amount = workbook.add_format({"bold": True, "bg_color": "#E8EEF8", "border": 1, "border_color": "#B8C5D8", "num_format": "#,##0;[Red]-#,##0", "align": "right"})
        total_text = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1B366A", "border": 1, "border_color": "#1B366A"})
        total_centered = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1B366A", "border": 1, "border_color": "#1B366A", "align": "center"})
        total_amount = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1B366A", "border": 1, "border_color": "#1B366A", "num_format": "#,##0;[Red]-#,##0", "align": "right"})

        row = 0
        sheet.merge_range(row, 0, row, 6, "COMPTE DE RÉSULTAT OHADA", title)
        sheet.set_row(row, 26)
        row += 1
        period_label = "Exercice du %s au %s" % (report_data["date_from"], report_data["date_to"])
        sheet.merge_range(row, 0, row, 6, period_label, subtitle)
        row += 2

        headers = ["RÉF.", "LIBELLÉS", "", "SIGNE", "NOTE", "EXERCICE %s" % report_data["year_n"], "EXERCICE %s" % report_data["year_n1"]]
        for column, label in enumerate(headers):
            sheet.write(row, column, label, header)
        sheet.set_row(row, 28)
        row += 1

        for line in report_data["lines"]:
            if line["line_type"] == "grand_total":
                text_format, centered_format, amount_format = total_text, total_centered, total_amount
            elif line["line_type"] == "subtotal":
                text_format, centered_format, amount_format = subtotal_text, subtotal_centered, subtotal_amount
            else:
                text_format, centered_format, amount_format = text, centered, amount

            sheet.write(row, 0, line["ref"], centered_format)
            sheet.write(row, 1, line["label"], text_format)
            sheet.write(row, 2, line["marker"], centered_format)
            sheet.write(row, 3, line["sign"], centered_format)
            sheet.write(row, 4, line["note"], centered_format)
            sheet.write_number(row, 5, line["amount"], amount_format)
            sheet.write_number(row, 6, line["amount_n1"], amount_format)
            row += 1

        sheet.freeze_panes(4, 0)
