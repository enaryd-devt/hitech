from datetime import datetime
from odoo import api, fields, models
from collections import defaultdict

class SalesPeriodicReport(models.AbstractModel):
    _name = 'primetech.sales.periodic.report'
    _inherit = 'primetech.sales.source'
    _description = 'Rapport Périodique des Ventes'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, partner_id=False, warehouse_ids=None, state_filter='all'):
        warehouse_ids = warehouse_ids or []
        sales = self._primetech_sales_lines(date_from, date_to, company_id, user_id, partner_id)
        sales_lines = []
        total_ht = 0.0
        total_ttc = 0.0
        total_qty = 0.0
        seller_summary = defaultdict(lambda: {'qty': 0.0, 'ht': 0.0, 'ttc': 0.0})
        customer_summary = defaultdict(lambda: {'ht': 0.0, 'ttc': 0.0})
        product_summary = defaultdict(lambda: {'qty': 0.0, 'ht': 0.0, 'product_id': False})
        for line in sales:
                seller = line['seller'].name or '-'
                customer = line['customer'].name or '-'
                qty, ht, ttc = line['qty'], line['ht'], line['ttc']
                total_qty += qty
                total_ht += ht
                total_ttc += ttc
                sales_lines.append({'invoice': line['document'], 'date': line['date'], 'customer': customer, 'seller': seller, 'product': line['product'].display_name, 'qty': qty, 'unit_price': line['unit_price'], 'ht': ht, 'ttc': ttc})
                seller_summary[seller]['qty'] += qty
                seller_summary[seller]['ht'] += ht
                seller_summary[seller]['ttc'] += ttc
                customer_summary[customer]['ht'] += ht
                customer_summary[customer]['ttc'] += ttc
                product_summary[line['product'].display_name]['qty'] += qty
                product_summary[line['product'].display_name]['ht'] += ht
                product_summary[line['product'].display_name]['product_id'] = line['product'].id
        period_end = datetime.combine(date_to, datetime.max.time())
        warehouses = self.env['stock.warehouse'].browse(warehouse_ids)
        for product in product_summary.values():
            record = self.env['product.product'].browse(product['product_id'])
            if warehouses:
                product['stock_remaining'] = sum(record.with_context(to_date=period_end, warehouse_id=warehouse.id).qty_available for warehouse in warehouses)
            else:
                product['stock_remaining'] = record.with_context(to_date=period_end).qty_available
        documents = {line['source'] + ':' + line['document'] for line in sales}
        summary = {'invoice_count': len(documents), 'customer_count': len({line['customer'].id for line in sales}), 'seller_count': len({line['seller'].id for line in sales}), 'turnover_ht': total_ht, 'turnover_ttc': total_ttc, 'qty_sold': total_qty, 'average_ticket': total_ht / len(documents) if documents else 0.0}
        top_customers = sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        top_products = sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        top_salespersons = sorted([{'seller': k, **v} for k, v in seller_summary.items()], key=lambda x: x['ht'], reverse=True)[:10]
        return {'summary': summary, 'sales_lines': sales_lines, 'seller_summary': sorted([{'seller': k, **v} for k, v in seller_summary.items()], key=lambda x: x['ht'], reverse=True), 'customer_summary': sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['ht'], reverse=True), 'product_summary': sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['ht'], reverse=True), 'top_customers': top_customers, 'top_products': top_products, 'top_salespersons': top_salespersons, 'warehouse_names': warehouses.mapped('display_name')}
