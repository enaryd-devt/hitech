from odoo import models

class SalesProfitabilityXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_profitability_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Rentabilité Commerciale XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.sales.profitability.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False, product_id=wizard.product_id.id if wizard.product_id else False)
        title = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'border': 1})
        header = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        cell = workbook.add_format({'border': 1})
        money = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Dashboard')
        sheet.set_column('A:B', 35)
        sheet.merge_range('A1:B1', 'RENTABILITE COMMERCIALE', title)
        summary = report_data['summary']
        row = 3
        dashboard = [('Nombre Commandes', summary['order_count']), ('Nombre Clients', summary['customer_count']), ("Chiffre d'Affaires", summary['revenue']), ('Coût Total', summary['cost']), ('Marge Brute', summary['margin']), ('Taux de Marge %', summary['margin_rate']), ('Panier Moyen', summary['average_order'])]
        for label, value in dashboard:
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value, money)
            row += 1
        sheet = workbook.add_worksheet('Produits')
        headers = ['Produit', 'Qté', 'CA', 'Coût', 'Marge', '% Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for line in report_data['product_ranking']:
            sheet.write(row, 0, line['product'], cell)
            sheet.write(row, 1, line['qty'], cell)
            sheet.write(row, 2, line['revenue'], money)
            sheet.write(row, 3, line['cost'], money)
            sheet.write(row, 4, line['margin'], money)
            sheet.write(row, 5, line['margin_rate'], money)
            row += 1
        sheet = workbook.add_worksheet('Clients')
        headers = ['Client', 'CA', 'Coût', 'Marge', '% Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for line in report_data['customer_ranking']:
            sheet.write(row, 0, line['customer'], cell)
            sheet.write(row, 1, line['revenue'], money)
            sheet.write(row, 2, line['cost'], money)
            sheet.write(row, 3, line['margin'], money)
            sheet.write(row, 4, line['margin_rate'], money)
            row += 1
        sheet = workbook.add_worksheet('Commerciaux')
        headers = ['Commercial', 'Commandes', 'CA', 'Coût', 'Marge', '% Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for line in report_data['salesperson_ranking']:
            sheet.write(row, 0, line['salesperson'], cell)
            sheet.write(row, 1, line['orders'], cell)
            sheet.write(row, 2, line['revenue'], money)
            sheet.write(row, 3, line['cost'], money)
            sheet.write(row, 4, line['margin'], money)
            sheet.write(row, 5, line['margin_rate'], money)
            row += 1
        sheet = workbook.add_worksheet('Evolution')
        headers = ['Mois', 'CA', 'Coût', 'Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for month, values in report_data['monthly_summary'].items():
            sheet.write(row, 0, month, cell)
            sheet.write(row, 1, values['revenue'], money)
            sheet.write(row, 2, values['cost'], money)
            sheet.write(row, 3, values['margin'], money)
            row += 1
        sheet = workbook.add_worksheet('Commandes')
        headers = ['Commande', 'Date', 'Client', 'Commercial', 'CA', 'Coût', 'Marge', '% Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for line in report_data['order_lines']:
            sheet.write(row, 0, line['order'], cell)
            sheet.write(row, 1, str(line['date']), cell)
            sheet.write(row, 2, line['customer'], cell)
            sheet.write(row, 3, line['salesperson'], cell)
            sheet.write(row, 4, line['revenue'], money)
            sheet.write(row, 5, line['cost'], money)
            sheet.write(row, 6, line['margin'], money)
            sheet.write(row, 7, line['margin_rate'], money)
            row += 1
        sheet = workbook.add_worksheet('Alertes')
        headers = ['Commande', 'Client', 'Marge']
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header)
        row = 1
        for line in report_data['negative_margin_orders']:
            sheet.write(row, 0, line['order'], cell)
            sheet.write(row, 1, line['customer'], cell)
            sheet.write(row, 2, line['margin'], money)
            row += 1
