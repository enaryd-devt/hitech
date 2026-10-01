from collections import defaultdict
from odoo import api, models

class SalesCustomerAnalysisReport(models.AbstractModel):
    _name = 'primetech.sales.customer.analysis.report'
    _description = 'Analyse Clients'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, partner_id=False):
        domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if user_id:
            domain.append(('invoice_user_id', '=', user_id))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        invoices = self.env['account.move'].search(domain)
        customer_summary = defaultdict(lambda: {'invoice_count': 0, 'qty': 0.0, 'ht': 0.0, 'ttc': 0.0})
        detail_lines = []
        total_ht = 0.0
        total_ttc = 0.0
        total_qty = 0.0
        for invoice in invoices:
            customer = invoice.partner_id.name or '-'
            customer_summary[customer]['invoice_count'] += 1
            for line in invoice.invoice_line_ids:
                qty = line.quantity
                ht = line.price_subtotal
                ttc = line.price_total
                total_qty += qty
                total_ht += ht
                total_ttc += ttc
                customer_summary[customer]['qty'] += qty
                customer_summary[customer]['ht'] += ht
                customer_summary[customer]['ttc'] += ttc
                detail_lines.append({'customer': customer, 'invoice': invoice.name, 'date': invoice.invoice_date, 'product': line.product_id.display_name, 'qty': qty, 'unit_price': line.price_unit, 'ht': ht, 'ttc': ttc})
        customer_lines = sorted([{'customer': customer, **values} for customer, values in customer_summary.items()], key=lambda x: x['ht'], reverse=True)
        summary = {'customer_count': len(customer_summary), 'invoice_count': len(invoices), 'turnover_ht': total_ht, 'turnover_ttc': total_ttc, 'qty_sold': total_qty, 'average_ticket': total_ht / len(invoices) if invoices else 0.0}
        return {'summary': summary, 'customer_lines': customer_lines, 'detail_lines': detail_lines, 'top_customers': customer_lines[:10]}
