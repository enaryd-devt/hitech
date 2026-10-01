# -*- coding: utf-8 -*-
from odoo import models

class PurchaseLeadXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_lead_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Lead Time XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        filters = (data or {}).get('filters', {})
        report_data = self.env['pt.purchase.lead'].get_report_data(filters)
        kpi = report_data.get('kpi', {})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        integer = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        decimal = workbook.add_format({'border': 1, 'num_format': '0.00'})
        sheet = workbook.add_worksheet('KPI')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 20)
        row = 0
        sheet.write(row, 0, "Délais d'Approvisionnement", title)
        row += 2
        rows = [('Nombre Commandes', kpi.get('order_count', 0), integer), ('Nombre Réceptions', kpi.get('receipt_count', 0), integer), ('Délai Moyen', kpi.get('avg_delay', 0), decimal), ('Délai Minimum', kpi.get('min_delay', 0), integer), ('Délai Maximum', kpi.get('max_delay', 0), integer), ('Commandes Hors Délai', kpi.get('late_orders', 0), integer)]
        for label, value, fmt in rows:
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value, fmt)
            row += 1
        sheet = workbook.add_worksheet('Analyse')
        headers = ['Fournisseur', 'Commandes', 'Délai Moyen', 'Délai Mini', 'Délai Maxi']
        for col, header_name in enumerate(headers):
            sheet.write(0, col, header_name, header)
        row = 1
        for line in report_data.get('supplier_analysis', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['order_count'], integer)
            sheet.write(row, 2, line['avg_delay'], decimal)
            sheet.write(row, 3, line['min_delay'], integer)
            sheet.write(row, 4, line['max_delay'], integer)
            row += 1
        sheet = workbook.add_worksheet('Top Rapides')
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Délai Moyen', header)
        row = 1
        for line in report_data.get('top_fast', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['avg_delay'], decimal)
            row += 1
        sheet = workbook.add_worksheet('Top Lents')
        sheet.write(0, 0, 'Fournisseur', header)
        sheet.write(0, 1, 'Délai Moyen', header)
        row = 1
        for line in report_data.get('top_slow', []):
            sheet.write(row, 0, line['supplier'], text)
            sheet.write(row, 1, line['avg_delay'], decimal)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        headers = ['Commande', 'Fournisseur', 'Date Commande', 'Date Réception', 'Délai (jours)', 'Montant']
        for col, header_name in enumerate(headers):
            sheet.write(0, col, header_name, header)
        row = 1
        for line in report_data.get('details', []):
            sheet.write(row, 0, line['order'], text)
            sheet.write(row, 1, line['supplier'], text)
            sheet.write(row, 2, str(line['order_date']), text)
            sheet.write(row, 3, str(line['receipt_date']), text)
            sheet.write(row, 4, line['delay'], integer)
            sheet.write(row, 5, line['amount'], amount)
            row += 1
