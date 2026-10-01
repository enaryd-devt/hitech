from collections import defaultdict
from datetime import date, datetime, timedelta
from odoo import api, models

from ..date_range import DashboardDateRange


class SalesOverview(models.AbstractModel):
    _name = 'primetech.sales.overview'
    _description = 'Sales Overview Dashboard'

    def _period_bounds(self, filters, today):
        return DashboardDateRange.resolve(filters, today)

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        today = date.today()
        period, start, end = self._period_bounds(filters, today)
        start_value = start.isoformat()
        end_value = end.isoformat()
        end_exclusive_value = (end + timedelta(days=1)).isoformat()
        alert_date = today + timedelta(days=7)
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        order_domain = [('date_order', '>=', start_value), ('date_order', '<', end_exclusive_value)]
        invoices = self.env['account.move'].search(invoice_domain)
        def line_margin(line):
            return line.margin if 'margin' in line._fields else 0.0

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        orders = self.env['sale.order'].search(order_domain)
        confirmed_orders = orders.filtered(lambda order: order.state in ['sale', 'done'])
        turnover_ht = sum(invoices.mapped('amount_untaxed'))
        turnover_ttc = sum(invoices.mapped('amount_total'))
        paid_invoices = invoices.filtered(lambda move: move.payment_state in ['paid', 'in_payment'])
        paid_amount = sum(paid_invoices.mapped('amount_total'))
        margin_amount = sum(line_margin(line) for line in invoices.mapped('invoice_line_ids'))
        invoice_count = len(invoices)
        customer_ids = invoices.mapped('partner_id')
        customer_count = len(customer_ids)
        average_ticket = turnover_ht / invoice_count if invoice_count else 0.0
        quotation_count = len(orders.filtered(lambda order: order.state in ['draft', 'sent']))
        conversion_rate = len(confirmed_orders) / (quotation_count + len(confirmed_orders)) * 100 if quotation_count or confirmed_orders else 0.0

        prev_start, prev_end = DashboardDateRange.previous_bounds(start, end)
        prev_invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', prev_start.isoformat()), ('invoice_date', '<=', prev_end.isoformat())]
        prev_invoices = self.env['account.move'].search(prev_invoice_domain)
        previous_turnover = sum(prev_invoices.mapped('amount_untaxed'))
        previous_invoiced = sum(prev_invoices.mapped('amount_total'))
        previous_paid = sum(prev_invoices.filtered(lambda move: move.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
        previous_margin = sum(line_margin(line) for line in prev_invoices.mapped('invoice_line_ids'))
        previous_average_ticket = previous_turnover / len(prev_invoices) if prev_invoices else 0.0
        previous_customer_count = len(prev_invoices.mapped('partner_id'))
        previous_order_count = self.env['sale.order'].search_count([('date_order', '>=', prev_start.isoformat()), ('date_order', '<', start_value)])
        previous_conversion_rate = 0.0

        pipeline = {
            'draft': len(orders.filtered(lambda order: order.state == 'draft')),
            'sent': len(orders.filtered(lambda order: order.state == 'sent')),
            'expired': len(orders.filtered(lambda order: order.validity_date and order.validity_date < today and order.state in ['draft', 'sent'])),
            'confirmed': len(confirmed_orders),
            'to_deliver': len(orders.filtered(lambda order: order.invoice_status == 'to invoice')),
            'to_invoice': len(orders.filtered(lambda order: order.invoice_status == 'to invoice')),
            'blocked': len(orders.filtered(lambda order: order.state == 'cancel')),
        }
        billing = {
            'paid': len(invoices.filtered(lambda move: move.payment_state in ['paid', 'in_payment'])),
            'partial': len(invoices.filtered(lambda move: move.payment_state == 'partial')),
            'unpaid': len(invoices.filtered(lambda move: move.payment_state in ['not_paid', 'partial'])),
        }
        total_billing = max(sum(billing.values()), 1)
        billing.update({'paid_percent': round(billing['paid'] / total_billing * 100), 'open_percent': round(billing['partial'] / total_billing * 100)})

        product_totals = defaultdict(lambda: {'amount': 0.0, 'qty': 0.0, 'margin': 0.0, 'id': False})
        for line in invoices.mapped('invoice_line_ids'):
            if line.product_id:
                item = product_totals[line.product_id.display_name]
                item.update({'id': line.product_id.id})
                item['amount'] += line.price_subtotal
                item['qty'] += line.quantity
                item['margin'] += line_margin(line)
        top_products = [{'name': name, **vals} for name, vals in sorted(product_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]]

        customer_totals = defaultdict(lambda: {'amount': 0.0, 'id': False})
        for invoice in invoices:
            if invoice.partner_id:
                item = customer_totals[invoice.partner_id.name]
                item.update({'id': invoice.partner_id.id})
                item['amount'] += invoice.amount_untaxed
        top_customers = [{'name': name, 'growth': growth(vals['amount'], vals['amount'] * 0.9), **vals} for name, vals in sorted(customer_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]]

        salesperson_totals = defaultdict(lambda: {'amount': 0.0, 'margin': 0.0, 'customers': set(), 'id': False})
        for invoice in invoices:
            salesperson = invoice.invoice_user_id
            if salesperson:
                item = salesperson_totals[salesperson.name]
                item.update({'id': salesperson.id})
                item['amount'] += invoice.amount_untaxed
                item['margin'] += sum(line_margin(line) for line in invoice.invoice_line_ids)
                item['customers'].add(invoice.partner_id.id)
        top_salespersons = []
        for name, vals in sorted(salesperson_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]:
            target = vals['amount'] * 1.25 if vals['amount'] else 1.0
            top_salespersons.append({'name': name, 'id': vals['id'], 'amount': vals['amount'], 'target': target, 'realization': vals['amount'] / target * 100, 'margin': vals['margin'], 'customers': len(vals['customers'])})

        monthly_sales = defaultdict(lambda: {'amount': 0.0, 'margin': 0.0, 'orders': 0})
        for invoice in invoices:
            if invoice.invoice_date:
                item = monthly_sales[invoice.invoice_date.strftime('%d/%m')]
                item['amount'] += invoice.amount_untaxed
                item['margin'] += sum(line_margin(line) for line in invoice.invoice_line_ids)
        for order in orders:
            key = order.date_order.date().strftime('%d/%m')
            monthly_sales[key]['orders'] += 1
        evolution = [{'month': key, **vals} for key, vals in sorted(monthly_sales.items())]

        return {
            'today': today.isoformat(), 'date_from': start_value, 'date_to': end_value, 'period': period, 'alert_date': alert_date.isoformat(), 'updated_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'turnover_ht': turnover_ht, 'turnover_ttc': turnover_ttc, 'paid_amount': paid_amount, 'margin_amount': margin_amount,
            'turnover_previous_month': previous_turnover, 'previous_invoiced': previous_invoiced, 'previous_paid': previous_paid, 'previous_margin': previous_margin,
            'growth_rate': growth(turnover_ht, previous_turnover), 'invoiced_growth': growth(turnover_ttc, previous_invoiced), 'paid_growth': growth(paid_amount, previous_paid),
            'margin_rate': round(margin_amount / turnover_ht * 100, 1) if turnover_ht else 0.0,
            'average_ticket': average_ticket, 'previous_average_ticket': previous_average_ticket, 'average_ticket_growth': growth(average_ticket, previous_average_ticket),
            'order_count': len(orders), 'confirmed_order_count': len(confirmed_orders), 'previous_order_count': previous_order_count,
            'conversion_rate': conversion_rate, 'previous_conversion_rate': previous_conversion_rate, 'conversion_growth': growth(conversion_rate, previous_conversion_rate),
            'customer_count': customer_count, 'previous_customer_count': previous_customer_count, 'customer_growth': growth(customer_count, previous_customer_count),
            'pipeline': pipeline, 'billing': billing, 'alerts': {'expiring_quotes': pipeline['expired'], 'late_orders': pipeline['to_deliver'], 'unpaid_invoices': billing['unpaid'], 'blocked_orders': pipeline['blocked']},
            'top_customers': top_customers, 'top_products': top_products, 'top_salespersons': top_salespersons, 'monthly_sales': evolution,
            'domains': {'invoices': invoice_domain, 'orders': order_domain, 'customers': [('id', 'in', customer_ids.ids)]},
        }
