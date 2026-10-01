# -*- coding: utf-8 -*-
from odoo import models

class CashPeriodXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.cash_period_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Periodic Cash XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[:1]
        filters = {'date_from': wizard.date_from, 'date_to': wizard.date_to, 'journal_ids': wizard.journal_ids.ids}
        report_data = self.env['pt.cash.period'].get_report_data(filters)
        title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'})
        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        text = workbook.add_format({'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        green_amount = workbook.add_format({'border': 1, 'font_color': '#16A34A', 'bold': True, 'num_format': '#,##0.00'})
        red_amount = workbook.add_format({'border': 1, 'font_color': '#DC2626', 'bold': True, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Synthèse')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 25)
        row = 0
        sheet.merge_range(row, 0, row, 1, 'RAPPORT PERIODIQUE DE TRESORERIE', title)
        row += 2
        kpi = report_data.get('kpi', {})
        rows = [('Solde Initial', kpi.get('opening_balance', 0), amount), ('Encaissements', kpi.get('incoming', 0), green_amount), ('Décaissements', kpi.get('outgoing', 0), red_amount), ('Solde Net', kpi.get('net', 0), amount), ('Solde Final', kpi.get('closing_balance', 0), amount)]
        for label, value, fmt in rows:
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value, fmt)
            row += 1
        sheet = workbook.add_worksheet('Mouvements')
        sheet.set_column('A:A', 15)
        sheet.set_column('B:B', 25)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:D', 30)
        sheet.set_column('E:E', 18)
        sheet.set_column('F:F', 20)
        sheet.set_column('G:G', 18)
        headers = ['Date', 'Journal', 'Référence', 'Partenaire', 'Type', 'Nature', 'Montant']
        for col, label in enumerate(headers):
            sheet.write(0, col, label, header)
        row = 1
        for line in report_data.get('movements', []):
            sheet.write(row, 0, str(line['date']), text)
            sheet.write(row, 1, line['journal'], text)
            sheet.write(row, 2, line['reference'], text)
            sheet.write(row, 3, line['partner'], text)
            sheet.write(row, 4, line['type'], text)
            sheet.write(row, 5, line['nature'], text)
            fmt = green_amount if line['type'] == 'Encaissement' else red_amount
            sheet.write(row, 6, line['amount'], fmt)
            row += 1
        sheet = workbook.add_worksheet('Synthèse Journaux')
        sheet.set_column('A:A', 30)
        sheet.set_column('B:F', 18)
        headers = ['Journal', 'Solde Initial', 'Encaissements', 'Décaissements', 'Solde Net', 'Solde Final']
        for col, label in enumerate(headers):
            sheet.write(0, col, label, header)
        row = 1
        for line in report_data.get('journal_summary', []):
            sheet.write(row, 0, line['journal'], text)
            sheet.write(row, 1, line['opening'], amount)
            sheet.write(row, 2, line['incoming'], green_amount)
            sheet.write(row, 3, line['outgoing'], red_amount)
            sheet.write(row, 4, line['net'], amount)
            sheet.write(row, 5, line['closing'], amount)
            row += 1
