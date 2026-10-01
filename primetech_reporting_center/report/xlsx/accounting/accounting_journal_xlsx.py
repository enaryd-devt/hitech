from odoo import models

class AccountingJournalXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.accounting_journal_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Journaux Comptables XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.accounting.journal'].get_journals_report(date_from=data.get('date_from'), date_to=data.get('date_to'), journal_ids=data.get('journal_ids'), posted_only=data.get('posted_only'))
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9'})
        text_format = workbook.add_format({'border': 1})
        amount_format = workbook.add_format({'border': 1, 'num_format': '#,##0', 'align': 'right'})
        total_format = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0'})
        for journal in report_data['journals']:
            sheet_name = f'{journal['journal_code']}'[:31]
            sheet = workbook.add_worksheet(sheet_name)
            sheet.set_column('A:A', 12)
            sheet.set_column('B:B', 20)
            sheet.set_column('C:C', 25)
            sheet.set_column('D:D', 15)
            sheet.set_column('E:E', 35)
            sheet.set_column('F:F', 40)
            sheet.set_column('G:H', 15)
            row = 0
            sheet.merge_range(row, 0, row, 7, f'JOURNAL {journal['journal_code']} - {journal['journal_name']}', title_format)
            row += 2
            sheet.write(row, 0, 'Date', header_format)
            sheet.write(row, 1, 'Pièce', header_format)
            sheet.write(row, 2, 'Tiers', header_format)
            sheet.write(row, 3, 'Compte', header_format)
            sheet.write(row, 4, 'Intitulé Compte', header_format)
            sheet.write(row, 5, 'Libellé', header_format)
            sheet.write(row, 6, 'Débit', header_format)
            sheet.write(row, 7, 'Crédit', header_format)
            row += 1
            for line in journal['entries']:
                sheet.write(row, 0, line['date'], text_format)
                sheet.write(row, 1, line['move'], text_format)
                sheet.write(row, 2, line['partner'], text_format)
                sheet.write(row, 3, line['account'], text_format)
                sheet.write(row, 4, line['account_name'], text_format)
                sheet.write(row, 5, line['label'], text_format)
                sheet.write_number(row, 6, line['debit'], amount_format)
                sheet.write_number(row, 7, line['credit'], amount_format)
                row += 1
            sheet.merge_range(row, 0, row, 5, 'TOTAL JOURNAL', total_format)
            sheet.write_number(row, 6, journal['total_debit'], total_format)
            sheet.write_number(row, 7, journal['total_credit'], total_format)
