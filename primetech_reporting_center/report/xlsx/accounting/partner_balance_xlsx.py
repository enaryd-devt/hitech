from odoo import models

class PartnerBalanceXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.partner_balance_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Balance des Tiers XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        wizard = wizard[0]
        report_data = self.env['primetech.partner.balance'].get_partner_balance(wizard.date_from, wizard.date_to, wizard.partner_type, wizard.posted_only)
        sheet = workbook.add_worksheet('Balance Tiers')
        bold = workbook.add_format({'bold': True, 'border': 1})
        amount = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        row = 0
        headers = ['Tiers', 'SI Débit', 'SI Crédit', 'Mvt Débit', 'Mvt Crédit', 'SF Débit', 'SF Crédit']
        for col, value in enumerate(headers):
            sheet.write(row, col, value, bold)
        row += 1
        for partner in report_data['partners']:
            sheet.write(row, 0, partner['partner_name'])
            sheet.write_number(row, 1, partner['opening_debit'], amount)
            sheet.write_number(row, 2, partner['opening_credit'], amount)
            sheet.write_number(row, 3, partner['period_debit'], amount)
            sheet.write_number(row, 4, partner['period_credit'], amount)
            sheet.write_number(row, 5, partner['closing_debit'], amount)
            sheet.write_number(row, 6, partner['closing_credit'], amount)
            row += 1
