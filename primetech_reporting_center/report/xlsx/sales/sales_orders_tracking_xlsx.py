from odoo import models

class SalesOrdersTrackingXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_orders_tracking_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Suivi des Commandes XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.sales.orders.tracking.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False, state=wizard.state)
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'border': 1})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        cell_format = workbook.add_format({'border': 1})
        money_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Dashboard')
        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 20)
        sheet.merge_range('A1:B1', 'SUIVI DES COMMANDES', title_format)
        summary = report_data['summary']
        row = 3
        sheet.write(row, 0, 'Nombre Commandes', header_format)
        sheet.write(row, 1, summary['order_count'], cell_format)
        row += 1
        sheet.write(row, 0, 'Nombre Clients', header_format)
        sheet.write(row, 1, summary['customer_count'], cell_format)
        row += 1
        sheet.write(row, 0, 'Quantité', header_format)
        sheet.write(row, 1, summary['qty'], cell_format)
        row += 1
        sheet.write(row, 0, 'CA HT', header_format)
        sheet.write(row, 1, summary['turnover_ht'], money_format)
        row += 1
        sheet.write(row, 0, 'CA TTC', header_format)
        sheet.write(row, 1, summary['turnover_ttc'], money_format)
        row += 1
        sheet.write(row, 0, 'Panier Moyen', header_format)
        sheet.write(row, 1, summary['average_ticket'], money_format)
        row += 1
        sheet.write(row, 0, 'Taux Confirmation %', header_format)
        sheet.write(row, 1, summary['confirmation_rate'], cell_format)
        sheet = workbook.add_worksheet('Commerciaux')
        sheet.set_column('A:D', 25)
        headers = ['Commercial', 'Commandes', 'Quantité', 'CA TTC', 'Panier Moyen']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['salesperson_ranking']:
            sheet.write(row, 0, line['salesperson'], cell_format)
            sheet.write(row, 1, line['order_count'], cell_format)
            sheet.write(row, 2, line['qty'], cell_format)
            sheet.write(row, 3, line['amount'], money_format)
            sheet.write(row, 4, line['average_ticket'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Clients')
        sheet.set_column('A:C', 35)
        headers = ['Client', 'Commandes', 'Montant TTC']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['customer_ranking']:
            sheet.write(row, 0, line['customer'], cell_format)
            sheet.write(row, 1, line['order_count'], cell_format)
            sheet.write(row, 2, line['amount'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Produits')
        headers = ['Produit', 'Quantité', 'Montant']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['product_ranking']:
            sheet.write(row, 0, line['product'], cell_format)
            sheet.write(row, 1, line['qty'], cell_format)
            sheet.write(row, 2, line['amount'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Commandes')
        sheet.set_column('A:H', 20)
        headers = ['Commande', 'Date', 'Client', 'Commercial', 'Etat', 'Quantité', 'HT', 'TTC']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['order_lines']:
            sheet.write(row, 0, line['name'], cell_format)
            sheet.write(row, 1, str(line['date']), cell_format)
            sheet.write(row, 2, line['customer'], cell_format)
            sheet.write(row, 3, line['salesperson'], cell_format)
            sheet.write(row, 4, line['state'], cell_format)
            sheet.write(row, 5, line['qty'], cell_format)
            sheet.write(row, 6, line['amount_ht'], money_format)
            sheet.write(row, 7, line['amount_ttc'], money_format)
            row += 1
