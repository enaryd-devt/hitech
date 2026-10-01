# -*- coding: utf-8 -*-
from odoo import models

class StockStatusXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_status_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        filters = data.get('filters', {})
        report_data = wizard.env['pt.stock.status'].get_report_data(filters)
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
        cell_format = workbook.add_format({'border': 1})
        number_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        money_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Résumé')
        sheet.merge_range('A1:F1', 'ETAT DE STOCK', title_format)
        row = 3
        sheet.write(row, 0, 'Date début', header_format)
        sheet.write(row, 1, str(filters.get('date_from', '')), cell_format)
        row += 1
        sheet.write(row, 0, 'Date fin', header_format)
        sheet.write(row, 1, str(filters.get('date_to', '')), cell_format)
        row += 2
        sheet.write(row, 0, 'Produits', header_format)
        sheet.write(row, 1, report_data['kpi']['products_count'], cell_format)
        row += 1
        sheet.write(row, 0, 'Quantité Totale', header_format)
        sheet.write(row, 1, report_data['kpi']['total_qty'], number_format)
        row += 1
        sheet.write(row, 0, 'Quantité Réservée', header_format)
        sheet.write(row, 1, report_data['kpi']['reserved_qty'], number_format)
        row += 1
        sheet.write(row, 0, 'Valeur Stock', header_format)
        sheet.write(row, 1, report_data['kpi']['stock_value'], money_format)
        row += 1
        sheet.write(row, 0, 'Produits en Rupture', header_format)
        sheet.write(row, 1, report_data['kpi']['out_of_stock'], cell_format)
        detail_sheet = workbook.add_worksheet('Etat Stock')
        columns = ['Produit', 'Référence', 'Catégorie', 'Emplacement', 'Disponible', 'Réservé', 'Entrant', 'Sortant', 'Valeur', 'Dernier Mouvement', 'Etat']
        for col, title in enumerate(columns):
            detail_sheet.write(0, col, title, header_format)
        state_normal = workbook.add_format({'border': 1, 'bg_color': '#D1FAE5', 'font_color': '#065F46'})
        state_low = workbook.add_format({'border': 1, 'bg_color': '#FEF3C7', 'font_color': '#92400E'})
        state_out = workbook.add_format({'border': 1, 'bg_color': '#FEE2E2', 'font_color': '#991B1B'})
        row = 1
        for line in report_data['lines']:
            detail_sheet.write(row, 0, line['product_name'], cell_format)
            detail_sheet.write(row, 1, line['default_code'], cell_format)
            detail_sheet.write(row, 2, line['category'], cell_format)
            detail_sheet.write(row, 3, line['location'], cell_format)
            detail_sheet.write_number(row, 4, line['available_qty'], number_format)
            detail_sheet.write_number(row, 5, line['reserved_qty'], number_format)
            detail_sheet.write_number(row, 6, line['incoming_qty'], number_format)
            detail_sheet.write_number(row, 7, line['outgoing_qty'], number_format)
            detail_sheet.write_number(row, 8, line['value'], money_format)
            detail_sheet.write(row, 9, line['last_move_date'], cell_format)
            if line['state'] == 'normal':
                state_format = state_normal
            elif line['state'] == 'faible':
                state_format = state_low
            else:
                state_format = state_out
            detail_sheet.write(row, 10, line['state'].upper(), state_format)
            row += 1
        detail_sheet.set_column(0, 0, 40)
        detail_sheet.set_column(1, 1, 18)
        detail_sheet.set_column(2, 2, 25)
        detail_sheet.set_column(3, 3, 30)
        detail_sheet.set_column(4, 8, 15)
        detail_sheet.set_column(9, 9, 18)
        detail_sheet.set_column(10, 10, 15)
        detail_sheet.autofilter(0, 0, row, len(columns) - 1)
        detail_sheet.freeze_panes(1, 0)
