from odoo import models

class InvoiceAnalysisXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.invoice_analysis_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Analyse de Facturation XLSX'

    def generate_xlsx_report(self, workbook, data, wizard):
        report_data = self.env['primetech.invoice.analysis.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, partner_id=wizard.partner_id.id if wizard.partner_id else False, user_id=wizard.user_id.id if wizard.user_id else False, move_type=wizard.move_type, payment_state=wizard.payment_state)
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'border': 1})
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        money_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Dashboard')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:B', 25)
        sheet.merge_range('A1:B1', 'ANALYSE DE FACTURATION', title_format)
        summary = report_data['summary']
        row = 3
        dashboard_lines = [('Nombre Factures', summary['invoice_count']), ('Nombre Clients', summary['customer_count']), ('Montant HT', summary['total_ht']), ('Montant TVA', summary['total_tax']), ('Montant TTC', summary['total_ttc']), ('Montant Payé', summary['paid_amount']), ('Montant Restant', summary['residual_amount']), ('Taux Encaissement %', summary['payment_rate']), ('Facture Moyenne', summary['average_invoice']), ('Montant Avoirs', summary['refund_amount'])]
        for label, value in dashboard_lines:
            sheet.write(row, 0, label, header_format)
            sheet.write(row, 1, value, money_format)
            row += 1
        sheet = workbook.add_worksheet('Paiements')
        sheet.set_column('A:C', 25)
        headers = ['Etat', 'Nombre', 'Montant']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for state, values in report_data['payment_summary'].items():
            sheet.write(row, 0, state, cell_format)
            sheet.write(row, 1, values['count'], cell_format)
            sheet.write(row, 2, values['amount'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Clients')
        sheet.set_column('A:C', 35)
        headers = ['Client', 'Factures', 'Montant TTC']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['customer_ranking']:
            sheet.write(row, 0, line['customer'], cell_format)
            sheet.write(row, 1, line['count'], cell_format)
            sheet.write(row, 2, line['amount'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Commerciaux')
        headers = ['Commercial', 'Factures', 'CA TTC', 'Encaissements']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['salesperson_ranking']:
            sheet.write(row, 0, line['salesperson'], cell_format)
            sheet.write(row, 1, line['count'], cell_format)
            sheet.write(row, 2, line['amount'], money_format)
            sheet.write(row, 3, line['paid'], money_format)
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
        sheet = workbook.add_worksheet('TVA')
        headers = ['Taxe', 'Base', 'Montant TVA']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for tax, values in report_data['tax_summary'].items():
            sheet.write(row, 0, tax, cell_format)
            sheet.write(row, 1, values['base'], money_format)
            sheet.write(row, 2, values['tax'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Factures')
        sheet.set_column('A:I', 22)
        headers = ['Facture', 'Date', 'Client', 'Commercial', 'Etat Paiement', 'HT', 'TVA', 'TTC', 'Solde']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['invoice_lines']:
            sheet.write(row, 0, line['invoice'], cell_format)
            sheet.write(row, 1, str(line['date']), cell_format)
            sheet.write(row, 2, line['customer'], cell_format)
            sheet.write(row, 3, line['salesperson'], cell_format)
            sheet.write(row, 4, line['payment_state'], cell_format)
            sheet.write(row, 5, line['ht'], money_format)
            sheet.write(row, 6, line['tax'], money_format)
            sheet.write(row, 7, line['ttc'], money_format)
            sheet.write(row, 8, line['residual'], money_format)
            row += 1
        sheet = workbook.add_worksheet('Alertes')
        headers = ['Facture', 'Client', 'Echéance', 'Solde']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        row = 1
        for line in report_data['alerts']['overdue']:
            sheet.write(row, 0, line['invoice'], cell_format)
            sheet.write(row, 1, line['customer'], cell_format)
            sheet.write(row, 2, str(line['due_date']), cell_format)
            sheet.write(row, 3, line['residual'], money_format)
            row += 1
