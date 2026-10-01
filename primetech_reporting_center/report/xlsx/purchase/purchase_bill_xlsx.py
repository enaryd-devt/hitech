# -*- coding: utf-8 -*-
from odoo import models

class PurchaseBillXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_bill_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Vendor Bills XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        filters = (data or {}).get('filters', {})
        report_data = self.env['pt.purchase.bill'].get_report_data(filters)
        kpi = report_data.get('kpi', {})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        integer = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        sheet = workbook.add_worksheet('KPI')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 25)
        row = 0
        sheet.write(row, 0, 'Rapport Factures Fournisseurs', title)
        row += 2
        kpi_rows = [('Nombre de factures', kpi.get('bill_count', 0), integer), ('Fournisseurs', kpi.get('supplier_count', 0), integer), ('Montant HT', kpi.get('total_untaxed', 0), amount), ('Taxes', kpi.get('total_tax', 0), amount), ('Montant TTC', kpi.get('total_amount', 0), amount), ('Montant payé', kpi.get('total_paid', 0), amount), ('Reste dû', kpi.get('total_residual', 0), amount), ('Factures payées', kpi.get('paid_count', 0), integer), ('Factures partielles', kpi.get('partial_count', 0), integer), ('Factures non payées', kpi.get('unpaid_count', 0), integer)]
        for label, value, fmt in kpi_rows:
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value, fmt)
            row += 1
        sheet = workbook.add_worksheet('Analyse Fournisseurs')
        sheet.set_column('A:A', 45)
        sheet.set_column('B:D', 20)
        headers = ['Fournisseur', 'Factures', 'Montant TTC', 'Reste dû']
        for col, header_text in enumerate(headers):
            sheet.write(0, col, header_text, header)
        row = 1
        for supplier, values in report_data.get('supplier_analysis', {}).items():
            sheet.write(row, 0, supplier, text)
            sheet.write(row, 1, values.get('count', 0), integer)
            sheet.write(row, 2, values.get('amount', 0), amount)
            sheet.write(row, 3, values.get('residual', 0), amount)
            row += 1
        sheet = workbook.add_worksheet('Evolution')
        sheet.set_column('A:A', 20)
        sheet.set_column('B:B', 25)
        sheet.write(0, 0, 'Mois', header)
        sheet.write(0, 1, 'Montant TTC', header)
        row = 1
        for month, amount_value in report_data.get('monthly_analysis', {}).items():
            sheet.write(row, 0, month, text)
            sheet.write(row, 1, amount_value, amount)
            row += 1
        sheet = workbook.add_worksheet('Détails')
        headers = ['Facture', 'Date', 'Échéance', 'Fournisseur', 'Référence', 'HT', 'Taxes', 'TTC', 'Payé', 'Solde', 'Statut']
        for col, header_text in enumerate(headers):
            sheet.write(0, col, header_text, header)
        row = 1
        for line in report_data.get('details', []):
            sheet.write(row, 0, line.get('number'), text)
            sheet.write(row, 1, str(line.get('date') or ''), text)
            sheet.write(row, 2, str(line.get('due_date') or ''), text)
            sheet.write(row, 3, line.get('supplier'), text)
            sheet.write(row, 4, line.get('reference'), text)
            sheet.write(row, 5, line.get('untaxed', 0), amount)
            sheet.write(row, 6, line.get('tax', 0), amount)
            sheet.write(row, 7, line.get('total', 0), amount)
            sheet.write(row, 8, line.get('paid', 0), amount)
            sheet.write(row, 9, line.get('residual', 0), amount)
            sheet.write(row, 10, line.get('payment_state'), text)
            row += 1
