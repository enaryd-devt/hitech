# -*- coding: utf-8 -*-
from odoo import models

class PurchaseReceiptXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_receipt_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Receipts XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        filters = (data or {}).get('filters', {})
        report_data = self.env['pt.purchase.recv'].get_report_data(filters)
        kpi = report_data.get('kpi', {})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        integer = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        sheet = workbook.add_worksheet('KPI')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 20)
        row = 0
        sheet.write(row, 0, 'Rapport des Réceptions', title)
        row += 2
        sheet.write(row, 0, 'Nombre de réceptions', header)
        sheet.write(row, 1, kpi.get('receipt_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'Fournisseurs', header)
        sheet.write(row, 1, kpi.get('supplier_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'Produits', header)
        sheet.write(row, 1, kpi.get('product_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'Terminées', header)
        sheet.write(row, 1, kpi.get('done_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'En attente', header)
        sheet.write(row, 1, kpi.get('waiting_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'Annulées', header)
        sheet.write(row, 1, kpi.get('cancel_count', 0), integer)
        row += 1
        sheet.write(row, 0, 'Qté Prévue', header)
        sheet.write(row, 1, kpi.get('total_expected_qty', 0), amount)
        row += 1
        sheet.write(row, 0, 'Qté Reçue', header)
        sheet.write(row, 1, kpi.get('total_received_qty', 0), amount)
        sheet = workbook.add_worksheet('Analyse Fournisseurs')
        sheet.set_column('A:A', 45)
        sheet.set_column('B:C', 20)
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Réceptions', header)
        sheet.write(0, 2, 'Quantité', header)
        row = 1
        for supplier, values in report_data.get('supplier_analysis', {}).items():
            sheet.write(row, 0, supplier, text)
            sheet.write(row, 1, values.get('count', 0), integer)
            sheet.write(row, 2, values.get('qty', 0), amount)
            row += 1
        sheet = workbook.add_worksheet('Analyse Produits')
        sheet.set_column('A:A', 50)
        sheet.set_column('B:B', 20)
        sheet.write(0, 0, 'Produit', header)
        sheet.write(0, 1, 'Quantité', header)
        row = 1
        for product, qty in report_data.get('product_analysis', {}).items():
            sheet.write(row, 0, product, text)
            sheet.write(row, 1, qty, amount)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        headers = ['Référence', 'Date', 'Fournisseur', 'Origine', 'Produit', 'Qté Prévue', 'Qté Reçue', 'Statut']
        for col, title_text in enumerate(headers):
            sheet.write(0, col, title_text, header)
        row = 1
        for line in report_data.get('details', []):
            sheet.write(row, 0, line.get('reference'), text)
            sheet.write(row, 1, str(line.get('date')), text)
            sheet.write(row, 2, line.get('supplier'), text)
            sheet.write(row, 3, line.get('origin'), text)
            sheet.write(row, 4, line.get('product'), text)
            sheet.write(row, 5, line.get('qty_expected', 0), amount)
            sheet.write(row, 6, line.get('qty_received', 0), amount)
            sheet.write(row, 7, line.get('state'), text)
            row += 1
