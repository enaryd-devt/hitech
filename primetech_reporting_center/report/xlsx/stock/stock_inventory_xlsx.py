# -*- coding: utf-8 -*-
from odoo import models

class StockInventoryXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_inventory_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Inventaire')
        row = 0
        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        cell_format = workbook.add_format({'border': 1})
        qty_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        report_data = self.env['pt.stock.inventory'].get_report_data(wizard._prepare_filters())
        sheet.merge_range(row, 0, row, 7, 'INVENTAIRE PHYSIQUE', title_format)
        row += 2
        inventory = report_data['inventory']
        for warehouse_name, warehouse_data in inventory.items():
            sheet.write(row, 0, f'ENTREPÔT : {warehouse_name}', title_format)
            row += 1
            for location_name, location_data in warehouse_data.items():
                sheet.write(row, 1, f'EMPLACEMENT : {location_name}', title_format)
                row += 1
                for category_name, category_data in location_data.items():
                    sheet.write(row, 2, f'CATÉGORIE : {category_name}', title_format)
                    row += 1
                    headers = ['Produit', 'Référence', 'Lot', 'Stock Disponible', 'Stock Réservé', 'Qté Comptée', 'Écart Observé', 'Observation']
                    for col, header in enumerate(headers):
                        sheet.write(row, col, header, header_format)
                    row += 1
                    for line in category_data:
                        sheet.write(row, 0, line['product_name'] if line['first_line'] else '', cell_format)
                        sheet.write(row, 1, line['default_code'] if line['first_line'] else '', cell_format)
                        sheet.write(row, 2, line['lot_name'], cell_format)
                        sheet.write_number(row, 3, line['qty_available'], qty_format)
                        sheet.write_number(row, 4, line['qty_reserved'], qty_format)
                        sheet.write(row, 5, '', cell_format)
                        sheet.write(row, 6, '', cell_format)
                        sheet.write(row, 7, '', cell_format)
                        row += 1
                    row += 2
        sheet.set_column('A:A', 40)
        sheet.set_column('B:B', 20)
        sheet.set_column('C:C', 20)
        sheet.set_column('D:E', 18)
        sheet.set_column('F:H', 20)
