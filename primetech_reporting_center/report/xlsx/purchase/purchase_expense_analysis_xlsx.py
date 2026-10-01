# -*- coding: utf-8 -*-
from odoo import models

class PurchaseExpenseXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_expense_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Expense XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        filters = (data or {}).get('filters', {})
        report_data = self.env['primetech.purchase.expense.report'].get_report_data(filters)
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        text_format = workbook.add_format({'border': 1})
        amount_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Catégories')
        sheet.set_column('A:D', 25)
        sheet.merge_range('A1:D1', 'ANALYSE DES DEPENSES PAR CATEGORIE', title_format)
        row = 3
        headers = ['Catégorie', 'Produits', 'Montant HT', '% Budget']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        for line in report_data['categories']:
            sheet.write(row, 0, line['category'], text_format)
            sheet.write(row, 1, line['product_count'], text_format)
            sheet.write(row, 2, line['amount'], amount_format)
            sheet.write(row, 3, line['percent'], amount_format)
            row += 1
        sheet = workbook.add_worksheet('Fournisseurs')
        sheet.set_column('A:D', 30)
        sheet.merge_range('A1:D1', 'ANALYSE DES DEPENSES PAR FOURNISSEUR', title_format)
        row = 3
        headers = ['Fournisseur', 'Nb Cmdes', 'Montant HT', 'Montant TTC']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        for line in report_data['suppliers']:
            sheet.write(row, 0, line['supplier'], text_format)
            sheet.write(row, 1, line['purchase_count'], text_format)
            sheet.write(row, 2, line['amount_ht'], amount_format)
            sheet.write(row, 3, line['amount_ttc'], amount_format)
            row += 1
        sheet = workbook.add_worksheet('Evolution')
        sheet.set_column('A:B', 25)
        sheet.merge_range('A1:B1', 'EVOLUTION MENSUELLE', title_format)
        row = 3
        sheet.write(row, 0, 'Période', header_format)
        sheet.write(row, 1, 'Montant TTC', header_format)
        row += 1
        for line in report_data['monthly']:
            sheet.write(row, 0, line['period'], text_format)
            sheet.write(row, 1, line['amount'], amount_format)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        sheet.set_column('A:F', 25)
        headers = ['Date', 'Fournisseur', 'Catégorie', 'Produit', 'Qté', 'Montant HT']
        row = 0
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        for line in report_data['lines']:
            sheet.write(row, 0, str(line['date'] or ''), text_format)
            sheet.write(row, 1, line['supplier'], text_format)
            sheet.write(row, 2, line['category'], text_format)
            sheet.write(row, 3, line['product'], text_format)
            sheet.write(row, 4, line['qty'], amount_format)
            sheet.write(row, 5, line['amount'], amount_format)
            row += 1
