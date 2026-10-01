# -*- coding: utf-8 -*-
from odoo import models

class StockValuationXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_valuation_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Stock Valuation XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Valorisation Stock')
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        text_format = workbook.add_format({'border': 1})
        amount_format = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        total_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        report_data = self.env['pt.stock.valuation'].get_report_data(data.get('filters', {}))
        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 1, 18)
        sheet.set_column(2, 2, 30)
        sheet.set_column(3, 5, 18)
        sheet.merge_range(0, 0, 0, 5, 'VALORISATION DU STOCK', title_format)
        row = 2
        sheet.write(row, 0, 'Produits', header_format)
        sheet.write(row, 1, report_data['kpi']['products_count'], text_format)
        sheet.write(row, 2, 'Quantité Totale', header_format)
        sheet.write(row, 3, report_data['kpi']['total_qty'], amount_format)
        sheet.write(row, 4, 'Valeur Stock', header_format)
        sheet.write(row, 5, report_data['kpi']['stock_value'], amount_format)
        row += 2
        sheet.merge_range(row, 0, row, 2, 'Produit le Plus Valorisé', header_format)
        sheet.merge_range(row, 3, row, 5, '{} ({:,.2f})'.format(report_data['kpi']['top_product'], report_data['kpi']['top_product_value']), text_format)
        row += 3
        headers = ['Produit', 'Référence', 'Catégorie', 'Quantité', 'Coût Unitaire', 'Valeur Stock']
        col = 0
        for header in headers:
            sheet.write(row, col, header, header_format)
            col += 1
        row += 1
        for line in report_data['lines']:
            sheet.write(row, 0, line['product_name'], text_format)
            sheet.write(row, 1, line['default_code'], text_format)
            sheet.write(row, 2, line['category'], text_format)
            sheet.write(row, 3, line['quantity'], amount_format)
            sheet.write(row, 4, line['cost_price'], amount_format)
            sheet.write(row, 5, line['stock_value'], amount_format)
            row += 1
        sheet.write(row, 0, 'TOTAL GENERAL', header_format)
        sheet.write_blank(row, 1, '', header_format)
        sheet.write_blank(row, 2, '', header_format)
        sheet.write(row, 3, report_data['kpi']['total_qty'], total_format)
        sheet.write_blank(row, 4, '', header_format)
        sheet.write(row, 5, report_data['kpi']['stock_value'], total_format)
