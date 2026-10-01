from odoo import models

class GeneralLedgerXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.general_ledger_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Grand Livre')
        sheet.set_column('A:A', 12)
        sheet.set_column('B:B', 8)
        sheet.set_column('C:C', 20)
        sheet.set_column('D:D', 45)
        sheet.set_column('E:E', 10)
        sheet.set_column('F:H', 18)
        title = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#EAEAEA'})
        account_header = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#D9D9D9', 'font_size': 11})
        total_format = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
        amount = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'right'})
        amount_bold = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'right', 'bold': True, 'bg_color': '#F2F2F2'})
        cell = workbook.add_format({'border': 1})
        ledger = self.env['primetech.general.ledger'].get_general_ledger(date_from=data.get('date_from'), date_to=data.get('date_to'), account_from=data.get('account_from'), account_to=data.get('account_to'), posted_only=data.get('posted_only'), hide_zero_balance=data.get('hide_zero_balance'))
        sheet.merge_range('A1:H1', 'GRAND LIVRE DES COMPTES', title)
        sheet.merge_range('A2:H2', f'Période du {data.get('date_from')} au {data.get('date_to')}', workbook.add_format({'align': 'center'}))
        row = 4
        for account in ledger['accounts']:
            sheet.merge_range(row, 0, row, 7, f'{account['code']} - {account['name']}', account_header)
            row += 1
            sheet.merge_range(row, 0, row, 6, "Solde d'ouverture", total_format)
            sheet.write_number(row, 7, account['opening_balance'], amount_bold)
            row += 1
            sheet.write(row, 0, 'Date', header)
            sheet.write(row, 1, 'C.J', header)
            sheet.write(row, 2, 'N° Pièce', header)
            sheet.write(row, 3, 'Libellé', header)
            sheet.write(row, 4, 'Let.', header)
            sheet.write(row, 5, 'Débit', header)
            sheet.write(row, 6, 'Crédit', header)
            sheet.write(row, 7, 'Solde', header)
            row += 1
            for line in account['lines']:
                sheet.write(row, 0, line['date'], cell)
                sheet.write(row, 1, line['journal'], cell)
                sheet.write(row, 2, line['piece'], cell)
                sheet.write(row, 3, line['label'], cell)
                sheet.write(row, 4, line['letter'], cell)
                sheet.write_number(row, 5, line['debit'], amount)
                sheet.write_number(row, 6, line['credit'], amount)
                sheet.write_number(row, 7, line['balance'], amount)
                row += 1
            sheet.merge_range(row, 0, row, 4, f'TOTAL COMPTE {account['code']}', total_format)
            sheet.write_number(row, 5, account['total_debit'], amount_bold)
            sheet.write_number(row, 6, account['total_credit'], amount_bold)
            sheet.write_number(row, 7, account['closing_balance'], amount_bold)
            row += 3
