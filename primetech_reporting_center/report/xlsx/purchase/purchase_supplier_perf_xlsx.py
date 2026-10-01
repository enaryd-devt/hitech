# -*- coding: utf-8 -*-
from odoo import models

class PurchaseSupplierPerformanceXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_supplier_perf_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Supplier Performance XLSX'

    def generate_xlsx_report(self, workbook, data, wizards):
        filters = (data or {}).get('filters', {})
        report_data = self.env['pt.purchase.supp'].get_report_data(filters)
        kpi = report_data.get('kpi', {})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        integer = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        percent = workbook.add_format({'border': 1, 'num_format': '0.00'})
        sheet = workbook.add_worksheet('KPI')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 20)
        row = 0
        sheet.write(row, 0, 'Performance Fournisseurs', title)
        row += 2
        rows = [('Nombre Fournisseurs', kpi.get('supplier_count', 0), integer), ('Commandes', kpi.get('order_count', 0), integer), ('Montant Achats', kpi.get('total_amount', 0), amount), ('Réceptions', kpi.get('receipt_count', 0), integer), ('Taux Réception %', kpi.get('receipt_rate', 0), percent), ('Délai Moyen', kpi.get('avg_delay', 0), percent)]
        for label, value, fmt in rows:
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value, fmt)
            row += 1
        sheet = workbook.add_worksheet('Analyse')
        headers = ['Fournisseur', 'Commandes', 'Montant', 'Réceptions', 'Qté Reçue', 'Taux %', 'Délai']
        for col, value in enumerate(headers):
            sheet.write(0, col, value, header)
        row = 1
        for line in report_data.get('supplier_analysis', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['order_count'], integer)
            sheet.write(row, 2, line['amount_total'], amount)
            sheet.write(row, 3, line['receipt_count'], integer)
            sheet.write(row, 4, line['qty_received'], amount)
            sheet.write(row, 5, line['receipt_rate'], percent)
            sheet.write(row, 6, line['avg_delay'], percent)
            row += 1
        sheet = workbook.add_worksheet('Top Montant')
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Montant', header)
        row = 1
        for line in report_data.get('top_amount', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['amount_total'], amount)
            row += 1
        sheet = workbook.add_worksheet('Top Réception')
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Taux %', header)
        row = 1
        for line in report_data.get('top_receipt', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['receipt_rate'], percent)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        headers = ['Fournisseur', 'Commande', 'Date Commande', 'Date Réception', 'Montant', 'Qté Reçue', 'Délai']
        for col, value in enumerate(headers):
            sheet.write(0, col, value, header)
        row = 1
        for line in report_data.get('details', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['order'], text)
            sheet.write(row, 2, str(line['order_date']), text)
            sheet.write(row, 3, str(line['receipt_date']), text)
            sheet.write(row, 4, line['amount'], amount)
            sheet.write(row, 5, line['qty_received'], amount)
            sheet.write(row, 6, line['delay'], integer)
            row += 1
