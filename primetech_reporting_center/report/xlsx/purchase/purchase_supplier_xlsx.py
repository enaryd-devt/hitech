# -*- coding: utf-8 -*-
from odoo import models

class PurchaseSupplierXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_supplier_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Supplier XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        filters = (data or {}).get('filters', {})
        report_data = self.env['primetech.purchase.supplier.report'].get_report_data(filters)
        sheet = workbook.add_worksheet('Achats Fournisseurs')
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        text_format = workbook.add_format({'border': 1})
        amount_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        total_format = workbook.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00'})
        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 35)
        sheet.set_column('C:C', 15)
        sheet.set_column('D:D', 15)
        sheet.set_column('E:G', 18)
        sheet.set_column('H:H', 20)
        sheet.merge_range('A1:H1', 'ACHATS PAR FOURNISSEUR', title_format)
        sheet.write('A3', 'Date début')
        sheet.write('B3', str(filters.get('date_from', '')))
        sheet.write('D3', 'Date fin')
        sheet.write('E3', str(filters.get('date_to', '')))
        sheet.write('A5', 'Fournisseurs')
        sheet.write('B5', report_data['supplier_count'])
        sheet.write('D5', 'Produits')
        sheet.write('E5', report_data['product_count'])
        sheet.write('G5', 'Commandes')
        sheet.write('H5', report_data['purchase_count'])
        row = 7
        headers = ['Fournisseur', 'Produit', 'Nb Cmdes', 'Quantité', 'Montant HT', 'TVA', 'Montant TTC', 'Dernier Achat']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        for line in report_data['lines']:
            sheet.write(row, 0, line['supplier'], text_format)
            sheet.write(row, 1, line['product'], text_format)
            sheet.write(row, 2, line['purchase_count'], text_format)
            sheet.write(row, 3, line['qty'], amount_format)
            sheet.write(row, 4, line['amount_ht'], amount_format)
            sheet.write(row, 5, line['amount_tax'], amount_format)
            sheet.write(row, 6, line['amount_ttc'], amount_format)
            sheet.write(row, 7, str(line['last_order'] or ''), text_format)
            row += 1
        sheet.write(row, 0, 'TOTAL GENERAL', total_format)
        sheet.write_blank(row, 1, '', total_format)
        sheet.write_blank(row, 2, '', total_format)
        sheet.write_blank(row, 3, '', total_format)
        sheet.write(row, 4, report_data['total_ht'], total_format)
        sheet.write(row, 5, report_data['total_tax'], total_format)
        sheet.write(row, 6, report_data['total_ttc'], total_format)
        sheet.write_blank(row, 7, '', total_format)
        sheet.freeze_panes(8, 0)
