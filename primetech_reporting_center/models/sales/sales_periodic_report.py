from datetime import datetime
from odoo import api, fields, models
from collections import defaultdict

class SalesPeriodicReport(models.AbstractModel):
    _name = 'primetech.sales.periodic.report'
    _description = 'Rapport Périodique des Ventes'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, partner_id=False, state_filter='all'):
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        if company_id:
            invoice_domain.append(('company_id', '=', company_id))
        if user_id:
            invoice_domain.append(('invoice_user_id', '=', user_id))
        if partner_id:
            invoice_domain.append(('partner_id', '=', partner_id))
        invoices = self.env['account.move'].search(invoice_domain)
        sales_lines = []
        total_ht = 0.0
        total_ttc = 0.0
        total_qty = 0.0
        seller_summary = defaultdict(lambda: {'qty': 0.0, 'ht': 0.0, 'ttc': 0.0})
        customer_summary = defaultdict(lambda: {'ht': 0.0, 'ttc': 0.0})
        product_summary = defaultdict(lambda: {'qty': 0.0, 'ht': 0.0})
        for invoice in invoices:
            seller = invoice.invoice_user_id.name or '-'
            customer = invoice.partner_id.name or '-'
            for line in invoice.invoice_line_ids:
                qty = line.quantity
                ht = line.price_subtotal
                ttc = line.price_total
                total_qty += qty
                total_ht += ht
                total_ttc += ttc
                sales_lines.append({'invoice': invoice.name, 'date': invoice.invoice_date, 'customer': customer, 'seller': seller, 'product': line.product_id.display_name, 'qty': qty, 'unit_price': line.price_unit, 'ht': ht, 'ttc': ttc})
                seller_summary[seller]['qty'] += qty
                seller_summary[seller]['ht'] += ht
                seller_summary[seller]['ttc'] += ttc
                customer_summary[customer]['ht'] += ht
                customer_summary[customer]['ttc'] += ttc
                product_summary[line.product_id.display_name]['qty'] += qty
                product_summary[line.product_id.display_name]['ht'] += ht
        summary = {'invoice_count': len(invoices), 'customer_count': len(invoices.mapped('partner_id')), 'seller_count': len(invoices.mapped('invoice_user_id')), 'turnover_ht': total_ht, 'turnover_ttc': total_ttc, 'qty_sold': total_qty, 'average_ticket': total_ht / len(invoices) if invoices else 0.0}
        top_customers = sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        top_products = sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        top_salespersons = sorted([{'seller': k, **v} for k, v in seller_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        return {'summary': summary, 'sales_lines': sales_lines, 'seller_summary': sorted([{'seller': k, **v} for k, v in seller_summary.items()], key=lambda x: x['ht'], reverse=True), 'customer_summary': sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['ht'], reverse=True), 'product_summary': sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['ht'], reverse=True), 'top_customers': top_customers, 'top_products': top_products, 'top_salespersons': top_salespersons}
