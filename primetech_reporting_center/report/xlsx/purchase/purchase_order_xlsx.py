# -*- coding: utf-8 -*-
from odoo import models

class PurchaseOrderXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_order_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Orders XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        filters = (data or {}).get('filters', {})
        report_data = self.env['pt.purchase.order'].get_report_data(filters)
        kpi = report_data.get('kpi', {})
        bold = workbook.add_format({'bold': True, 'border': 1})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        amount = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text = workbook.add_format({'border': 1})
        sheet = workbook.add_worksheet('KPI')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 20)
        row = 0
        sheet.write(row, 0, "Rapport Commandes d'Achat", bold)
        row += 2
        sheet.write(row, 0, 'Nombre de commandes', bold)
        sheet.write(row, 1, kpi.get('order_count', 0))
        row += 1
        sheet.write(row, 0, 'Montant HT', bold)
        sheet.write(row, 1, kpi.get('total_untaxed', 0), amount)
        row += 1
        sheet.write(row, 0, 'Taxes', bold)
        sheet.write(row, 1, kpi.get('total_tax', 0), amount)
        row += 1
        sheet.write(row, 0, 'Montant TTC', bold)
        sheet.write(row, 1, kpi.get('total_amount', 0), amount)
        row += 1
        sheet.write(row, 0, 'Montant moyen', bold)
        sheet.write(row, 1, kpi.get('avg_amount', 0), amount)
        row += 1
        sheet.write(row, 0, 'Fournisseurs', bold)
        sheet.write(row, 1, kpi.get('supplier_count', 0))
        row += 1
        sheet.write(row, 0, 'Produits', bold)
        sheet.write(row, 1, kpi.get('product_count', 0))
        sheet = workbook.add_worksheet('Analyse Fournisseurs')
        sheet.set_column('A:A', 50)
        sheet.set_column('B:B', 20)
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Montant', header)
        row = 1
        for supplier, total in report_data.get('supplier_analysis', {}).items():
            sheet.write(row, 0, supplier, text)
            sheet.write(row, 1, total, amount)
            row += 1
        sheet = workbook.add_worksheet('Analyse Acheteurs')
        sheet.set_column('A:A', 50)
        sheet.set_column('B:B', 20)
        sheet.write(0, 0, 'Acheteur', header)
        sheet.write(0, 1, 'Montant', header)
        row = 1
        for buyer, total in report_data.get('buyer_analysis', {}).items():
            sheet.write(row, 0, buyer, text)
            sheet.write(row, 1, total, amount)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        headers = ['Référence', 'Date', 'Fournisseur', 'Acheteur', 'Société', 'HT', 'Taxes', 'TTC', 'État']
        for col, title in enumerate(headers):
            sheet.write(0, col, title, header)
        row = 1
        for line in report_data.get('details', []):
            sheet.write(row, 0, line.get('name'), text)
            sheet.write(row, 1, str(line.get('date')), text)
            sheet.write(row, 2, line.get('supplier'), text)
            sheet.write(row, 3, line.get('buyer'), text)
            sheet.write(row, 4, line.get('company'), text)
            sheet.write(row, 5, line.get('untaxed', 0), amount)
            sheet.write(row, 6, line.get('tax', 0), amount)
            sheet.write(row, 7, line.get('total', 0), amount)
            sheet.write(row, 8, line.get('state'), text)
            row += 1
