from collections import defaultdict
from odoo import api, models, fields

class SalesOrdersTrackingReport(models.AbstractModel):
    _name = 'primetech.sales.orders.tracking.report'
    _description = 'Suivi des Commandes'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, partner_id=False, state=False):
        domain = [('date_order', '>=', date_from), ('date_order', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if user_id:
            domain.append(('user_id', '=', user_id))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        if state:
            domain.append(('state', '=', state))
        orders = self.env['sale.order'].search(domain, order='date_order desc')
        total_ht = 0.0
        total_ttc = 0.0
        total_qty = 0.0
        cancelled_amount = 0.0
        customer_ids = set()
        salesperson_summary = defaultdict(lambda: {'order_count': 0, 'amount': 0.0, 'qty': 0.0})
        customer_summary = defaultdict(lambda: {'order_count': 0, 'amount': 0.0})
        product_summary = defaultdict(lambda: {'qty': 0.0, 'amount': 0.0})
        status_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        delayed_orders = []
        cancelled_orders = []
        order_lines = []
        product_lines = []
        largest_order = None
        for order in orders:
            customer_ids.add(order.partner_id.id)
            total_ht += order.amount_untaxed
            total_ttc += order.amount_total
            salesperson = order.user_id.name if order.user_id else 'Non affecté'
            qty_order = sum(order.order_line.mapped('product_uom_qty'))
            total_qty += qty_order
            salesperson_summary[salesperson]['order_count'] += 1
            salesperson_summary[salesperson]['amount'] += order.amount_total
            salesperson_summary[salesperson]['qty'] += qty_order
            customer_summary[order.partner_id.name]['order_count'] += 1
            customer_summary[order.partner_id.name]['amount'] += order.amount_total
            status_summary[order.state]['count'] += 1
            status_summary[order.state]['amount'] += order.amount_total
            if largest_order is None or order.amount_total > largest_order['amount']:
                largest_order = {'name': order.name, 'customer': order.partner_id.name, 'amount': order.amount_total}
            if order.state == 'cancel':
                cancelled_amount += order.amount_total
                cancelled_orders.append({'name': order.name, 'customer': order.partner_id.name, 'amount': order.amount_total})
            age = (fields.Date.today() - order.date_order.date()).days
            if order.state in ['draft', 'sent'] and age > 7:
                delayed_orders.append({'name': order.name, 'customer': order.partner_id.name, 'days': age, 'amount': order.amount_total})
            order_lines.append({'name': order.name, 'date': order.date_order, 'customer': order.partner_id.name, 'salesperson': salesperson, 'state': order.state, 'qty': qty_order, 'amount_ht': order.amount_untaxed, 'amount_ttc': order.amount_total, 'line_count': len(order.order_line)})
            for line in order.order_line:
                product_summary[line.product_id.display_name]['qty'] += line.product_uom_qty
                product_summary[line.product_id.display_name]['amount'] += line.price_total
                product_lines.append({'order': order.name, 'customer': order.partner_id.name, 'product': line.product_id.display_name, 'qty': line.product_uom_qty, 'unit_price': line.price_unit, 'discount': line.discount, 'subtotal': line.price_subtotal, 'total': line.price_total})
        salesperson_ranking = sorted([{'salesperson': k, **v, 'average_ticket': v['amount'] / v['order_count'] if v['order_count'] else 0} for k, v in salesperson_summary.items()], key=lambda x: x['amount'], reverse=True)
        customer_ranking = sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['amount'], reverse=True)
        product_ranking = sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['amount'], reverse=True)
        confirmed_orders = len(orders.filtered(lambda x: x.state in ['sale', 'done']))
        confirmation_rate = confirmed_orders * 100 / len(orders) if orders else 0
        summary = {'order_count': len(orders), 'customer_count': len(customer_ids), 'qty': total_qty, 'turnover_ht': total_ht, 'turnover_ttc': total_ttc, 'average_ticket': total_ttc / len(orders) if orders else 0, 'confirmation_rate': confirmation_rate, 'cancelled_count': len(cancelled_orders), 'cancelled_amount': cancelled_amount, 'largest_order': largest_order}
        return {'summary': summary, 'status_summary': dict(status_summary), 'salesperson_ranking': salesperson_ranking, 'customer_ranking': customer_ranking[:20], 'product_ranking': product_ranking[:20], 'alerts': {'delayed_orders': delayed_orders, 'cancelled_orders': cancelled_orders}, 'order_lines': order_lines, 'product_lines': product_lines}
