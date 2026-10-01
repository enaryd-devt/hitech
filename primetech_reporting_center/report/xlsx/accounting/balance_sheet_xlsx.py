from odoo import models

class BalanceSheetXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.balance_sheet_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Bilan OHADA XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.balance.sheet'].get_balance_sheet(date_to=data.get('date_to'), posted_only=data.get('posted_only'))
        sheet = workbook.add_worksheet('Bilan OHADA')
        title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'border': 1})
        section = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#D9D9D9'})
        header = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#EFEFEF'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0', 'align': 'right'})
        total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F5F5F5', 'num_format': '#,##0'})
        grand_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#D9D9D9', 'num_format': '#,##0'})
        sheet.set_column('A:A', 10)
        sheet.set_column('B:B', 45)
        sheet.set_column('C:C', 10)
        sheet.set_column('D:F', 18)
        sheet.set_column('G:G', 18)
        row = 0
        sheet.merge_range(row, 0, row, 6, 'BILAN OHADA', title)
        row += 2
        sheet.write(row, 0, 'REF', header)
        sheet.write(row, 1, 'LIBELLE', header)
        sheet.write(row, 2, 'NOTE', header)
        sheet.write(row, 3, 'BRUT', header)
        sheet.write(row, 4, 'AMORT.', header)
        sheet.write(row, 5, 'NET', header)
        sheet.write(row, 6, 'N-1', header)
        row += 1
        for line in report_data['actif']:
            if line['line_type'] == 'section':
                fmt = section
            elif line['line_type'] == 'grand_total':
                fmt = grand_total
            elif line['line_type'] == 'total':
                fmt = total
            else:
                fmt = text
            sheet.write(row, 0, line.get('ref', ''), fmt)
            sheet.write(row, 1, line.get('label', ''), fmt)
            sheet.write(row, 2, line.get('note', ''), fmt)
            sheet.write_number(row, 3, line.get('brut', 0.0), amount)
            sheet.write_number(row, 4, line.get('amort', 0.0), amount)
            sheet.write_number(row, 5, line.get('net', 0.0), amount)
            sheet.write_number(row, 6, line.get('net_n1', 0.0), amount)
            row += 1
        row += 2
        sheet.merge_range(row, 0, row, 6, 'PASSIF', title)
        row += 1
        sheet.write(row, 0, 'REF', header)
        sheet.write(row, 1, 'LIBELLE', header)
        sheet.write(row, 2, 'NOTE', header)
        sheet.write(row, 3, 'BRUT', header)
        sheet.write(row, 4, 'AMORT.', header)
        sheet.write(row, 5, 'NET', header)
        sheet.write(row, 6, 'N-1', header)
        row += 1
        for line in report_data['passif']:
            if line['line_type'] == 'section':
                fmt = section
            elif line['line_type'] == 'grand_total':
                fmt = grand_total
            elif line['line_type'] == 'total':
                fmt = total
            else:
                fmt = text
            sheet.write(row, 0, line.get('ref', ''), fmt)
            sheet.write(row, 1, line.get('label', ''), fmt)
            sheet.write(row, 2, line.get('note', ''), fmt)
            sheet.write_number(row, 3, line.get('brut', 0.0), amount)
            sheet.write_number(row, 4, line.get('amort', 0.0), amount)
            sheet.write_number(row, 5, line.get('net', 0.0), amount)
            sheet.write_number(row, 6, line.get('net_n1', 0.0), amount)
            row += 1
