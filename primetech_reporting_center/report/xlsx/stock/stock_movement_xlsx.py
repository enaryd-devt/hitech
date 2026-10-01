# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models

class StockMovementXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_movement_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['pt.stock.movement'].get_report_data(wizard._prepare_filters())
        sheet = workbook.add_worksheet('Mouvements')
        row = 0
        title_format = workbook.add_format({'bold': True, 'font_size': 16})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        cell_format = workbook.add_format({'border': 1})
        qty_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        total_format = workbook.add_format({'bold': True, 'border': 1})
        sheet.merge_range(row, 0, row, 10, 'MOUVEMENTS DE STOCK', title_format)
        row += 2
        sheet.write(row, 0, 'Date impression : %s' % datetime.now().strftime('%d/%m/%Y %H:%M'))
        row += 1
        sheet.write(row, 0, 'Société')
        sheet.write(row, 1, wizard.company_id.name)
        row += 3
        for product in report_data['products']:
            sheet.merge_range(row, 0, row, 10, product['product_name'], title_format)
            row += 1
            sheet.write(row, 0, 'Référence')
            sheet.write(row, 1, product['default_code'])
            row += 1
            headers = ['Date', 'Partenaire', 'Document', 'Origine', 'Destination', 'Lot', 'Entrée', 'Sortie', 'Solde', 'Coût', 'Valorisation']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
            row += 1
            for line in product['lines']:
                sheet.write(row, 0, str(line['date']))
                sheet.write(row, 1, line['partner_name'])
                sheet.write(row, 2, line['document'])
                sheet.write(row, 3, line['source_name'])
                sheet.write(row, 4, line['destination_name'])
                sheet.write(row, 5, line['lot_name'])
                sheet.write_number(row, 6, line['qty_in'], qty_format)
                sheet.write_number(row, 7, line['qty_out'], qty_format)
                sheet.write_number(row, 8, line['balance'], qty_format)
                sheet.write_number(row, 9, line['cost'], qty_format)
                sheet.write_number(row, 10, line['valuation'], qty_format)
                row += 1
            sheet.write(row, 0, 'TOTAL ARTICLE', total_format)
            sheet.write_number(row, 6, product['total_in'], total_format)
            sheet.write_number(row, 7, product['total_out'], total_format)
            sheet.write_number(row, 8, product['balance'], total_format)
            sheet.write_number(row, 10, product['valuation'], total_format)
            row += 3
        sheet.set_column('A:A', 18)
        sheet.set_column('B:B', 25)
        sheet.set_column('C:C', 25)
        sheet.set_column('D:E', 35)
        sheet.set_column('F:F', 18)
        sheet.set_column('G:K', 18)
