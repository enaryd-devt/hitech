from odoo import models

class SalesCustomerAnalysisXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_customer_analysis_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Analyse Clients XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Analyse Clients')
        title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header = workbook.add_format({'bold': True, 'border': 1})
        cell = workbook.add_format({'border': 1})
        report_data = self.env['primetech.sales.customer.analysis.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False)
        row = 0
        sheet.merge_range(row, 0, row, 5, 'ANALYSE CLIENTS', title)
        row += 2
        headers = ['Client', 'Factures', 'Quantité', 'CA HT', 'CA TTC']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header)
        row += 1
        for line in report_data['customer_lines']:
            sheet.write(row, 0, line['customer'], cell)
            sheet.write(row, 1, line['invoice_count'], cell)
            sheet.write(row, 2, line['qty'], cell)
            sheet.write(row, 3, line['ht'], cell)
            sheet.write(row, 4, line['ttc'], cell)
            row += 1
        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 4, 15)
