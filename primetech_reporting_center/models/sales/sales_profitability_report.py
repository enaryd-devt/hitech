from collections import defaultdict
from odoo import api
from odoo import fields
from odoo import models

class SalesProfitabilityReport(models.AbstractModel):
    _name = 'primetech.sales.profitability.report'
    _description = 'Rentabilité Commerciale'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, user_id=False, partner_id=False, product_id=False):
        domain = [('state', 'in', ['sale', 'done']), ('date_order', '>=', date_from), ('date_order', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if user_id:
            domain.append(('user_id', '=', user_id))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        orders = self.env['sale.order'].search(domain)
        total_revenue = 0.0
        total_cost = 0.0
        total_margin = 0.0
        customer_ids = set()
        product_summary = defaultdict(lambda: {'qty': 0.0, 'revenue': 0.0, 'cost': 0.0, 'margin': 0.0})
        customer_summary = defaultdict(lambda: {'revenue': 0.0, 'cost': 0.0, 'margin': 0.0})
        salesperson_summary = defaultdict(lambda: {'revenue': 0.0, 'cost': 0.0, 'margin': 0.0, 'orders': 0})
        monthly_summary = defaultdict(lambda: {'revenue': 0.0, 'cost': 0.0, 'margin': 0.0})
        order_lines = []
        negative_margin_orders = []
        for order in orders:
            customer_ids.add(order.partner_id.id)
            order_revenue = 0.0
            order_cost = 0.0
            salesperson = order.user_id.name if order.user_id else 'Non affecté'
            month_key = order.date_order.strftime('%Y-%m')
            for line in order.order_line:
                if product_id and line.product_id.id != product_id:
                    continue
                revenue = line.price_subtotal
                cost = line.product_uom_qty * line.product_id.standard_price
                margin = revenue - cost
                total_revenue += revenue
                total_cost += cost
                total_margin += margin
                order_revenue += revenue
                order_cost += cost
                product_name = line.product_id.display_name
                product_summary[product_name]['qty'] += line.product_uom_qty
                product_summary[product_name]['revenue'] += revenue
                product_summary[product_name]['cost'] += cost
                product_summary[product_name]['margin'] += margin
                customer_summary[order.partner_id.name]['revenue'] += revenue
                customer_summary[order.partner_id.name]['cost'] += cost
                customer_summary[order.partner_id.name]['margin'] += margin
                salesperson_summary[salesperson]['revenue'] += revenue
                salesperson_summary[salesperson]['cost'] += cost
                salesperson_summary[salesperson]['margin'] += margin
                monthly_summary[month_key]['revenue'] += revenue
                monthly_summary[month_key]['cost'] += cost
                monthly_summary[month_key]['margin'] += margin
            order_margin = order_revenue - order_cost
            salesperson_summary[salesperson]['orders'] += 1
            margin_rate = order_margin * 100 / order_revenue if order_revenue else 0
            order_lines.append({'order': order.name, 'date': order.date_order.date(), 'customer': order.partner_id.name, 'salesperson': salesperson, 'revenue': order_revenue, 'cost': order_cost, 'margin': order_margin, 'margin_rate': margin_rate})
            if order_margin < 0:
                negative_margin_orders.append({'order': order.name, 'customer': order.partner_id.name, 'margin': order_margin})
        summary = {'order_count': len(orders), 'customer_count': len(customer_ids), 'revenue': total_revenue, 'cost': total_cost, 'margin': total_margin, 'margin_rate': total_margin * 100 / total_revenue if total_revenue else 0, 'average_order': total_revenue / len(orders) if orders else 0}
        product_ranking = []
        for product, values in product_summary.items():
            values['margin_rate'] = values['margin'] * 100 / values['revenue'] if values['revenue'] else 0
            product_ranking.append({'product': product, **values})
        customer_ranking = []
        for customer, values in customer_summary.items():
            values['margin_rate'] = values['margin'] * 100 / values['revenue'] if values['revenue'] else 0
            customer_ranking.append({'customer': customer, **values})
        salesperson_ranking = []
        for salesperson, values in salesperson_summary.items():
            values['margin_rate'] = values['margin'] * 100 / values['revenue'] if values['revenue'] else 0
            salesperson_ranking.append({'salesperson': salesperson, **values})
        return {'summary': summary, 'product_ranking': sorted(product_ranking, key=lambda x: x['margin'], reverse=True), 'customer_ranking': sorted(customer_ranking, key=lambda x: x['margin'], reverse=True), 'salesperson_ranking': sorted(salesperson_ranking, key=lambda x: x['margin'], reverse=True), 'monthly_summary': dict(monthly_summary), 'order_lines': order_lines, 'negative_margin_orders': negative_margin_orders}
