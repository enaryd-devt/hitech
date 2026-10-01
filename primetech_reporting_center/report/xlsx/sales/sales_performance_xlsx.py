from odoo import models

class SalesPerformanceXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_performance_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Performance Commerciale XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.sales.performance.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False)
        sheet = workbook.add_worksheet('Performance Commerciale')
        title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header = workbook.add_format({'bold': True, 'border': 1})
        cell = workbook.add_format({'border': 1})
        money = workbook.add_format({'border': 1, 'num_format': '# ##0'})
        row = 0
        sheet.merge_range(row, 0, row, 5, 'PERFORMANCE COMMERCIALE', title)
        row += 2
        sheet.write(row, 0, 'Date début', header)
        sheet.write(row, 1, str(wizard.date_from), cell)
        sheet.write(row, 2, 'Date fin', header)
        sheet.write(row, 3, str(wizard.date_to), cell)
        row += 2
        summary = report_data['summary']
        sheet.write(row, 0, 'Nb commerciaux', header)
        sheet.write(row, 1, summary['salesman_count'], cell)
        sheet.write(row, 2, 'Nb factures', header)
        sheet.write(row, 3, summary['invoice_count'], cell)
        row += 1
        sheet.write(row, 0, 'Qté vendue', header)
        sheet.write(row, 1, summary['qty_sold'], cell)
        sheet.write(row, 2, 'CA HT', header)
        sheet.write(row, 3, summary['turnover_ht'], money)
        row += 1
        sheet.write(row, 0, 'CA TTC', header)
        sheet.write(row, 1, summary['turnover_ttc'], money)
        row += 3
        sheet.write(row, 0, 'CLASSEMENT COMMERCIAUX', header)
        row += 1
        headers = ['Commercial', 'Factures', 'Quantité', 'CA HT', 'CA TTC']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header)
        row += 1
        for line in report_data['performance_lines']:
            sheet.write(row, 0, line['salesman'], cell)
            sheet.write(row, 1, line['invoice_count'], cell)
            sheet.write(row, 2, line['qty'], cell)
            sheet.write(row, 3, line['ht'], money)
            sheet.write(row, 4, line['ttc'], money)
            row += 1
        row += 2
        sheet.write(row, 0, 'DETAIL DES VENTES', header)
        row += 1
        headers = ['Facture', 'Date', 'Client', 'Commercial', 'Qté', 'HT', 'TTC']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header)
        row += 1
        for line in report_data['detail_lines']:
            sheet.write(row, 0, line['invoice'], cell)
            sheet.write(row, 1, str(line['date']), cell)
            sheet.write(row, 2, line['customer'], cell)
            sheet.write(row, 3, line['salesman'], cell)
            sheet.write(row, 4, line['qty'], cell)
            sheet.write(row, 5, line['ht'], money)
            sheet.write(row, 6, line['ttc'], money)
            row += 1
        sheet.set_column('A:A', 25)
        sheet.set_column('B:B', 15)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:D', 25)
        sheet.set_column('E:G', 15)
