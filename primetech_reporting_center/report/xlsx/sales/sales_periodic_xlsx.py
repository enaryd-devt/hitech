from datetime import datetime
from odoo import models

class SalesPeriodicXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_periodic_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Rapport XLSX Périodique des Ventes'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Rapport Ventes')
        title = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        cell = workbook.add_format({'border': 1})
        money = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        report_data = self.env['primetech.sales.periodic.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False, state_filter=wizard.state_filter)
        summary = report_data['summary']
        row = 0
        sheet.merge_range(row, 0, row, 8, 'RAPPORT PERIODIQUE DES VENTES', title)
        row += 2
        sheet.write(row, 0, f'Période : {wizard.date_from} au {wizard.date_to}')
        sheet.write(row, 6, 'Imprimé le : ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        row += 3
        sheet.write(row, 0, 'RESUME GENERAL', header)
        row += 1
        sheet.write(row, 0, 'Nombre Factures', cell)
        sheet.write(row, 1, summary['invoice_count'], cell)
        row += 1
        sheet.write(row, 0, 'Nombre Clients', cell)
        sheet.write(row, 1, summary['customer_count'], cell)
        row += 1
        sheet.write(row, 0, 'Nombre Commerciaux', cell)
        sheet.write(row, 1, summary['seller_count'], cell)
        row += 1
        sheet.write(row, 0, 'CA HT', cell)
        sheet.write(row, 1, summary['turnover_ht'], money)
        row += 1
        sheet.write(row, 0, 'CA TTC', cell)
        sheet.write(row, 1, summary['turnover_ttc'], money)
        row += 1
        sheet.write(row, 0, 'Quantité Vendue', cell)
        sheet.write(row, 1, summary['qty_sold'], cell)
        row += 3
        sheet.write(row, 0, 'DETAIL DES VENTES', header)
        row += 1
        columns = ['Facture', 'Date', 'Client', 'Commercial', 'Produit', 'Qté', 'PU', 'HT', 'TTC']
        for col, name in enumerate(columns):
            sheet.write(row, col, name, header)
        row += 1
        for line in report_data['sales_lines']:
            sheet.write(row, 0, line['invoice'], cell)
            sheet.write(row, 1, str(line['date']), cell)
            sheet.write(row, 2, line['customer'], cell)
            sheet.write(row, 3, line['seller'], cell)
            sheet.write(row, 4, line['product'], cell)
            sheet.write(row, 5, line['qty'], cell)
            sheet.write(row, 6, line['unit_price'], money)
            sheet.write(row, 7, line['ht'], money)
            sheet.write(row, 8, line['ttc'], money)
            row += 1
        sheet.set_column('A:A', 18)
        sheet.set_column('B:B', 15)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:D', 25)
        sheet.set_column('E:E', 40)
        sheet.set_column('F:F', 10)
        sheet.set_column('G:I', 18)
