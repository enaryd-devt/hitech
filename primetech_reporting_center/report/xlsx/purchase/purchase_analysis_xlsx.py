# -*- coding: utf-8 -*-
from odoo import models

class PurchaseAnalysisXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_analysis_xlsx_report'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Analysis XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        filters = data.get('filters', {})
        report_data = wizard.env['primetech.purchase.analysis.report'].get_report_data(filters)
        sheet = workbook.add_worksheet('Analyse Achats')
        title = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        header = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1, 'align': 'center'})
        cell = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet.set_column('A:A', 15)
        sheet.set_column('B:B', 18)
        sheet.set_column('C:C', 25)
        sheet.set_column('D:D', 30)
        sheet.set_column('E:E', 12)
        sheet.set_column('F:F', 15)
        sheet.set_column('G:G', 15)
        sheet.set_column('H:H', 15)
        sheet.set_column('I:I', 15)
        sheet.merge_range('A1:I1', 'ANALYSE DES ACHATS', title)
        row = 3
        sheet.write(row, 0, 'Nb Achats', header)
        sheet.write(row, 1, report_data['purchase_count'], cell)
        sheet.write(row, 2, 'Fournisseurs', header)
        sheet.write(row, 3, report_data['supplier_count'], cell)
        sheet.write(row, 4, 'Produits', header)
        sheet.write(row, 5, report_data['product_count'], cell)
        row += 2
        sheet.write(row, 0, 'Total HT', header)
        sheet.write(row, 1, report_data['total_ht'], amount)
        sheet.write(row, 2, 'TVA', header)
        sheet.write(row, 3, report_data['total_tax'], amount)
        sheet.write(row, 4, 'Total TTC', header)
        sheet.write(row, 5, report_data['total_ttc'], amount)
        row += 4
        columns = ['Date', 'Commande', 'Fournisseur', 'Produit', 'Qté', 'Prix Unit.', 'Sous Total', 'Taxes', 'Total']
        for col_num, col_name in enumerate(columns):
            sheet.write(row, col_num, col_name, header)
        row += 1
        for line in report_data['purchase_lines']:
            sheet.write(row, 0, str(line['date'])[:10], cell)
            sheet.write(row, 1, line['order'], cell)
            sheet.write(row, 2, line['supplier'], cell)
            sheet.write(row, 3, line['product'], cell)
            sheet.write(row, 4, line['qty'], cell)
            sheet.write(row, 5, line['price_unit'], amount)
            sheet.write(row, 6, line['subtotal'], amount)
            sheet.write(row, 7, line['tax'], amount)
            sheet.write(row, 8, line['total'], amount)
            row += 1
