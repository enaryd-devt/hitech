from collections import defaultdict
from odoo import api, models

class SalesProductAnalysisReport(models.AbstractModel):
    _name = 'primetech.sales.product.analysis.report'
    _description = 'Analyse Produits'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, product_id=False):
        domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if user_id:
            domain.append(('invoice_user_id', '=', user_id))
        invoices = self.env['account.move'].search(domain)
        product_summary = defaultdict(lambda: {'qty': 0.0, 'ht': 0.0, 'ttc': 0.0, 'invoice_count': 0})
        detail_lines = []
        total_qty = 0.0
        total_ht = 0.0
        total_ttc = 0.0
        for invoice in invoices:
            for line in invoice.invoice_line_ids:
                if product_id and line.product_id.id != product_id:
                    continue
                product = line.product_id.display_name or '-'
                qty = line.quantity
                ht = line.price_subtotal
                ttc = line.price_total
                total_qty += qty
                total_ht += ht
                total_ttc += ttc
                product_summary[product]['qty'] += qty
                product_summary[product]['ht'] += ht
                product_summary[product]['ttc'] += ttc
                product_summary[product]['invoice_count'] += 1
                detail_lines.append({'invoice': invoice.name, 'date': invoice.invoice_date, 'customer': invoice.partner_id.name, 'product': product, 'qty': qty, 'unit_price': line.price_unit, 'ht': ht, 'ttc': ttc})
        product_lines = sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['ht'], reverse=True)
        summary = {'product_count': len(product_summary), 'invoice_count': len(invoices), 'qty_sold': total_qty, 'turnover_ht': total_ht, 'turnover_ttc': total_ttc}
        return {'summary': summary, 'product_lines': product_lines, 'detail_lines': detail_lines, 'top_products': product_lines[:10]}
