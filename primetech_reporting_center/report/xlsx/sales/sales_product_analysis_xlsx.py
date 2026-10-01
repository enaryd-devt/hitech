from odoo import models

class SalesProductAnalysisXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_product_analysis_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Analyse Produits XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Analyse Produits')
        title_style = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'border': 1})
        header_style = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9EAD3'})
        cell_style = workbook.add_format({'border': 1})
        money_style = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        report_data = self.env['primetech.sales.product.analysis.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, product_id=wizard.product_id.id if wizard.product_id else False)
        summary = report_data['summary']
        row = 0
        sheet.merge_range(row, 0, row, 6, 'ANALYSE DES PRODUITS', title_style)
        row += 2
        sheet.write(row, 0, 'Date début', header_style)
        sheet.write(row, 1, str(wizard.date_from), cell_style)
        sheet.write(row, 3, 'Date fin', header_style)
        sheet.write(row, 4, str(wizard.date_to), cell_style)
        row += 1
        sheet.write(row, 0, 'Société', header_style)
        sheet.write(row, 1, wizard.company_id.name or '', cell_style)
        sheet.write(row, 3, 'Commercial', header_style)
        sheet.write(row, 4, wizard.user_id.name if wizard.user_id else 'Tous', cell_style)
        row += 3
        sheet.merge_range(row, 0, row, 3, 'RÉSUMÉ', header_style)
        row += 1
        sheet.write(row, 0, 'Nb Produits', header_style)
        sheet.write(row, 1, summary['product_count'], cell_style)
        sheet.write(row, 2, 'Nb Factures', header_style)
        sheet.write(row, 3, summary['invoice_count'], cell_style)
        row += 1
        sheet.write(row, 0, 'Qté Vendue', header_style)
        sheet.write(row, 1, summary['qty_sold'], money_style)
        sheet.write(row, 2, 'CA HT', header_style)
        sheet.write(row, 3, summary['turnover_ht'], money_style)
        sheet.write(row, 4, 'CA TTC', header_style)
        sheet.write(row, 5, summary['turnover_ttc'], money_style)
        row += 3
        sheet.merge_range(row, 0, row, 5, 'TOP PRODUITS', header_style)
        row += 1
        headers = ['Produit', 'Qté', 'CA HT', 'CA TTC', 'Nb Ventes']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header_style)
        row += 1
        for line in report_data['top_products']:
            sheet.write(row, 0, line['product'], cell_style)
            sheet.write(row, 1, line['qty'], money_style)
            sheet.write(row, 2, line['ht'], money_style)
            sheet.write(row, 3, line['ttc'], money_style)
            sheet.write(row, 4, line['invoice_count'], cell_style)
            row += 1
        row += 2
        sheet.merge_range(row, 0, row, 7, 'DETAIL DES VENTES', header_style)
        row += 1
        headers = ['Facture', 'Date', 'Client', 'Produit', 'Qté', 'PU', 'Montant HT', 'Montant TTC']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header_style)
        row += 1
        for line in report_data['detail_lines']:
            sheet.write(row, 0, line['invoice'], cell_style)
            sheet.write(row, 1, str(line['date']), cell_style)
            sheet.write(row, 2, line['customer'], cell_style)
            sheet.write(row, 3, line['product'], cell_style)
            sheet.write(row, 4, line['qty'], money_style)
            sheet.write(row, 5, line['unit_price'], money_style)
            sheet.write(row, 6, line['ht'], money_style)
            sheet.write(row, 7, line['ttc'], money_style)
            row += 1
        sheet.set_column('A:A', 18)
        sheet.set_column('B:B', 15)
        sheet.set_column('C:C', 35)
        sheet.set_column('D:D', 40)
        sheet.set_column('E:H', 15)
