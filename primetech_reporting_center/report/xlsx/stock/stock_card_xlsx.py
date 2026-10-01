# -*- coding: utf-8 -*-
from odoo import models

class StockCardXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_card_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Stock Card XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Fiche Stock')
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        text_format = workbook.add_format({'border': 1})
        number_format = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        report_data = self.env['pt.stock.card'].get_report_data(data.get('filters', {}))
        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 40)
        sheet.set_column(3, 6, 18)
        sheet.merge_range(0, 0, 0, 6, 'FICHE DE STOCK', title_format)
        row = 2
        sheet.write(row, 0, 'Articles', header_format)
        sheet.write(row, 1, report_data['kpi']['products_count'], text_format)
        sheet.write(row, 2, 'Quantité Totale', header_format)
        sheet.write(row, 3, report_data['kpi']['total_qty'], number_format)
        sheet.write(row, 4, 'Valeur Stock', header_format)
        sheet.write(row, 5, report_data['kpi']['stock_value'], number_format)
        row += 3
        headers = ['Article', 'Référence', 'Lots', 'Qté', 'Coût Unitaire', 'Prix Vente', 'Valeur Stock']
        col = 0
        for header in headers:
            sheet.write(row, col, header, header_format)
            col += 1
        row += 1
        for line in report_data['lines']:
            lots_text = ''
            if line['lots']:
                lots_text = '\n'.join(['{} : {:,.2f}'.format(lot['lot_name'], lot['quantity']) for lot in line['lots']])
            sheet.write(row, 0, line['product_name'], text_format)
            sheet.write(row, 1, line['default_code'], text_format)
            sheet.write(row, 2, lots_text, text_format)
            sheet.write(row, 3, line['quantity'], number_format)
            sheet.write(row, 4, line['cost_price'], number_format)
            sheet.write(row, 5, line['sale_price'], number_format)
            sheet.write(row, 6, line['stock_value'], number_format)
            row += 1
        sheet.write(row, 0, 'TOTAL GENERAL', header_format)
        sheet.write_blank(row, 1, '', header_format)
        sheet.write_blank(row, 2, '', header_format)
        sheet.write(row, 3, report_data['kpi']['total_qty'], header_format)
        sheet.write_blank(row, 4, '', header_format)
        sheet.write_blank(row, 5, '', header_format)
        sheet.write(row, 6, report_data['kpi']['stock_value'], header_format)
