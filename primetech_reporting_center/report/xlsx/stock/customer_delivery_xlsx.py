# -*- coding: utf-8 -*-
from odoo import models


class CustomerDeliveryXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.customer_delivery_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Excel des produits déstockés et livrés'

    def generate_xlsx_report(self, workbook, data, wizard):
        report = self.env['pt.customer.delivery.report'].get_report_data(wizard._prepare_filters())
        sheet = workbook.add_worksheet('Livraisons clients')
        title = workbook.add_format({'bold': True, 'font_size': 16})
        header = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1})
        cell = workbook.add_format({'border': 1})
        number = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet.merge_range(0, 0, 0, 6, 'PRODUITS DÉSTOCKÉS / LIVRÉS', title)
        sheet.write(2, 0, 'Période'); sheet.write(2, 1, '%s au %s' % (wizard.date_from, wizard.date_to))
        headers = ['Date', 'Document', 'Client', 'Article', 'Qté livrée', 'UdM', 'Stock restant']
        for col, value in enumerate(headers): sheet.write(4, col, value, header)
        row = 5
        for line in report['lines']:
            sheet.write(row, 0, str(line['date'])); sheet.write(row, 1, line['document'], cell); sheet.write(row, 2, line['customer'], cell); sheet.write(row, 3, line['product'].display_name, cell); sheet.write_number(row, 4, line['quantity'], number); sheet.write(row, 5, line['uom'], cell); sheet.write_number(row, 6, line['stock_remaining'], number); row += 1
        sheet.set_column('A:A', 14); sheet.set_column('B:C', 24); sheet.set_column('D:D', 35); sheet.set_column('E:G', 16)
