from collections import defaultdict
from odoo import api, models

class SalesPerformanceReport(models.AbstractModel):
    _name = 'primetech.sales.performance.report'
    _description = 'Performance Commerciale'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False):
        domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if user_id:
            domain.append(('invoice_user_id', '=', user_id))
        invoices = self.env['account.move'].search(domain)
        sales_summary = defaultdict(lambda: {'invoice_count': 0, 'qty': 0.0, 'ht': 0.0, 'ttc': 0.0})
        total_qty = 0.0
        total_ht = 0.0
        total_ttc = 0.0
        detail_lines = []
        for invoice in invoices:
            salesman = invoice.invoice_user_id.name or 'Non affecté'
            qty = sum(invoice.invoice_line_ids.mapped('quantity'))
            ht = invoice.amount_untaxed
            ttc = invoice.amount_total
            total_qty += qty
            total_ht += ht
            total_ttc += ttc
            sales_summary[salesman]['invoice_count'] += 1
            sales_summary[salesman]['qty'] += qty
            sales_summary[salesman]['ht'] += ht
            sales_summary[salesman]['ttc'] += ttc
            detail_lines.append({'invoice': invoice.name, 'date': invoice.invoice_date, 'customer': invoice.partner_id.name, 'salesman': salesman, 'qty': qty, 'ht': ht, 'ttc': ttc})
        performance_lines = sorted([{'salesman': k, **v} for k, v in sales_summary.items()], key=lambda x: x['ht'], reverse=True)
        summary = {'salesman_count': len(sales_summary), 'invoice_count': len(invoices), 'qty_sold': total_qty, 'turnover_ht': total_ht, 'turnover_ttc': total_ttc}
        return {'summary': summary, 'performance_lines': performance_lines, 'detail_lines': detail_lines, 'top_salesmen': performance_lines[:10]}
