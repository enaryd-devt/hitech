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
        """Build the sales dashboard from customer invoices.

        The deployment creates sales directly from customer invoices; sale
        orders are deliberately not used as a reporting source here.
        """
        filters = filters or {}
        today = date.today()
        period, start, end = self._period_bounds(filters, today)
        start_value, end_value = start.isoformat(), end.isoformat()
        alert_date = today + timedelta(days=7)
        AccountMove = self.env['account.move']
        PosOrder = self.env['pos.order'] if 'pos.order' in self.env.registry else False
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        # A POS ticket that generated an invoice must be counted once only,
        # from the POS source below.
        if 'pos_order_ids' in AccountMove._fields:
            invoice_domain.append(('pos_order_ids', '=', False))
        draft_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'draft'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        invoices = AccountMove.search(invoice_domain)
        draft_invoices = AccountMove.search(draft_domain)
        pos_domain = [('state', 'in', ['paid', 'done', 'invoiced']), ('date_order', '>=', start_value), ('date_order', '<', (end + timedelta(days=1)).isoformat())] if PosOrder else []
        pos_orders = PosOrder.search(pos_domain) if PosOrder else self.env['account.move'].browse()

        def line_margin(line):
            return line.margin if 'margin' in line._fields else 0.0

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        pos_turnover_ttc = sum(pos_orders.mapped('amount_total'))
        pos_turnover_ht = sum((order.amount_total - order.amount_tax) for order in pos_orders)
        turnover_ht = sum(invoices.mapped('amount_untaxed')) + pos_turnover_ht
        turnover_ttc = sum(invoices.mapped('amount_total')) + pos_turnover_ttc
        paid_amount = sum(invoice.amount_total - invoice.amount_residual for invoice in invoices) + pos_turnover_ttc
        margin_amount = sum(line_margin(line) for line in invoices.mapped('invoice_line_ids'))
        invoice_count = len(invoices) + len(pos_orders)
        customer_ids = invoices.mapped('partner_id') | pos_orders.mapped('partner_id')
        customer_count = len(customer_ids)
        average_ticket = turnover_ht / invoice_count if invoice_count else 0.0
        collection_rate = paid_amount / turnover_ttc * 100 if turnover_ttc else 0.0

        prev_start, prev_end = DashboardDateRange.previous_bounds(start, end)
        previous_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', prev_start.isoformat()), ('invoice_date', '<=', prev_end.isoformat())]
        if 'pos_order_ids' in AccountMove._fields:
            previous_domain.append(('pos_order_ids', '=', False))
        prev_invoices = AccountMove.search(previous_domain)
        previous_pos_domain = [('state', 'in', ['paid', 'done', 'invoiced']), ('date_order', '>=', prev_start.isoformat()), ('date_order', '<', start_value)] if PosOrder else []
        previous_pos_orders = PosOrder.search(previous_pos_domain) if PosOrder else self.env['account.move'].browse()
        previous_turnover = sum(prev_invoices.mapped('amount_untaxed')) + sum(order.amount_total - order.amount_tax for order in previous_pos_orders)
        previous_invoiced = sum(prev_invoices.mapped('amount_total')) + sum(previous_pos_orders.mapped('amount_total'))
        previous_paid = sum(invoice.amount_total - invoice.amount_residual for invoice in prev_invoices) + sum(previous_pos_orders.mapped('amount_total'))
        previous_margin = sum(line_margin(line) for line in prev_invoices.mapped('invoice_line_ids'))
        previous_average_ticket = previous_turnover / (len(prev_invoices) + len(previous_pos_orders)) if prev_invoices or previous_pos_orders else 0.0
        previous_customer_count = len(prev_invoices.mapped('partner_id') | previous_pos_orders.mapped('partner_id'))
        previous_collection_rate = previous_paid / previous_invoiced * 100 if previous_invoiced else 0.0
        overdue_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial']), ('invoice_date_due', '<', today.isoformat())]
        open_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]
        cancelled_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'cancel'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        pipeline = {
            'draft': len(draft_invoices), 'sent': AccountMove.search_count(overdue_domain),
            'expired': AccountMove.search_count(overdue_domain), 'confirmed': invoice_count,
            'to_deliver': len(invoices.filtered(lambda move: move.payment_state == 'partial')),
            'to_invoice': AccountMove.search_count(open_domain), 'blocked': AccountMove.search_count(cancelled_domain),
        }
        billing = {
            'paid': len(invoices.filtered(lambda move: move.payment_state in ['paid', 'in_payment'])),
            'partial': len(invoices.filtered(lambda move: move.payment_state == 'partial')),
            'unpaid': len(invoices.filtered(lambda move: move.payment_state in ['not_paid', 'partial'])),
        }
        total_billing = max(sum(billing.values()), 1)
        billing.update({'paid_percent': round(billing['paid'] / total_billing * 100), 'open_percent': round(billing['partial'] / total_billing * 100)})

        product_totals = defaultdict(lambda: {'amount': 0.0, 'qty': 0.0, 'margin': 0.0, 'id': False})
        for line in invoices.mapped('invoice_line_ids').filtered(lambda row: row.product_id and not row.display_type):
            item = product_totals[line.product_id.display_name]
            item.update({'id': line.product_id.id})
            item['amount'] += line.price_subtotal
            item['qty'] += line.quantity
            item['margin'] += line_margin(line)
        for line in pos_orders.mapped('lines').filtered(lambda row: row.product_id):
            item = product_totals[line.product_id.display_name]
            item.update({'id': line.product_id.id})
            item['amount'] += line.price_subtotal_incl
            item['qty'] += line.qty
        top_products = [{'name': name, **values} for name, values in sorted(product_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]]

        customer_totals = defaultdict(lambda: {'amount': 0.0, 'id': False})
        salesperson_totals = defaultdict(lambda: {'amount': 0.0, 'margin': 0.0, 'customers': set(), 'id': False})
        monthly_sales = defaultdict(lambda: {'amount': 0.0, 'margin': 0.0, 'orders': 0})
        for invoice in invoices:
            if invoice.partner_id:
                customer_totals[invoice.partner_id.name].update({'id': invoice.partner_id.id})
                customer_totals[invoice.partner_id.name]['amount'] += invoice.amount_untaxed
            if invoice.invoice_user_id:
                salesperson = invoice.invoice_user_id
                item = salesperson_totals[salesperson.name]
                item.update({'id': salesperson.id})
                item['amount'] += invoice.amount_untaxed
                item['margin'] += sum(line_margin(line) for line in invoice.invoice_line_ids)
                item['customers'].add(invoice.partner_id.id)
            if invoice.invoice_date:
                item = monthly_sales[invoice.invoice_date.strftime('%d/%m')]
                item['amount'] += invoice.amount_untaxed
                item['margin'] += sum(line_margin(line) for line in invoice.invoice_line_ids)
                item['orders'] += 1
        for order in pos_orders:
            if order.partner_id:
                customer_totals[order.partner_id.name].update({'id': order.partner_id.id})
                customer_totals[order.partner_id.name]['amount'] += order.amount_total - order.amount_tax
            if order.user_id:
                salesperson = order.user_id
                item = salesperson_totals[salesperson.name]
                item.update({'id': salesperson.id})
                item['amount'] += order.amount_total - order.amount_tax
                item['customers'].add(order.partner_id.id)
            if order.date_order:
                item = monthly_sales[order.date_order.strftime('%d/%m')]
                item['amount'] += order.amount_total - order.amount_tax
                item['orders'] += 1
        top_customers = [{'name': name, 'growth': growth(value['amount'], 0.0), **value} for name, value in sorted(customer_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]]
        top_salespersons = []
        for name, value in sorted(salesperson_totals.items(), key=lambda item: item[1]['amount'], reverse=True)[:5]:
            target = value['amount'] * 1.25 if value['amount'] else 1.0
            top_salespersons.append({'name': name, 'id': value['id'], 'amount': value['amount'], 'target': target, 'realization': value['amount'] / target * 100, 'margin': value['margin'], 'customers': len(value['customers'])})

        return {
            'today': today.isoformat(), 'date_from': start_value, 'date_to': end_value, 'period': period, 'alert_date': alert_date.isoformat(), 'updated_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'turnover_ht': turnover_ht, 'turnover_ttc': turnover_ttc, 'paid_amount': paid_amount, 'margin_amount': margin_amount,
            'turnover_previous_month': previous_turnover, 'previous_invoiced': previous_invoiced, 'previous_paid': previous_paid, 'previous_margin': previous_margin,
            'growth_rate': growth(turnover_ht, previous_turnover), 'invoiced_growth': growth(turnover_ttc, previous_invoiced), 'paid_growth': growth(paid_amount, previous_paid),
            'margin_rate': round(margin_amount / turnover_ht * 100, 1) if turnover_ht else 0.0,
            'average_ticket': average_ticket, 'previous_average_ticket': previous_average_ticket, 'average_ticket_growth': growth(average_ticket, previous_average_ticket),
            'order_count': invoice_count, 'confirmed_order_count': invoice_count, 'previous_order_count': len(prev_invoices) + len(previous_pos_orders),
            'conversion_rate': collection_rate, 'previous_conversion_rate': previous_collection_rate, 'conversion_growth': growth(collection_rate, previous_collection_rate),
            'customer_count': customer_count, 'previous_customer_count': previous_customer_count, 'customer_growth': growth(customer_count, previous_customer_count),
            'pipeline': pipeline, 'billing': billing,
            'alerts': {'expiring_quotes': pipeline['draft'], 'late_orders': pipeline['expired'], 'unpaid_invoices': billing['unpaid'], 'blocked_orders': pipeline['blocked']},
            'top_customers': top_customers, 'top_products': top_products, 'top_salespersons': top_salespersons,
            'monthly_sales': [{'month': key, **value} for key, value in sorted(monthly_sales.items())],
            'domains': {'invoices': invoice_domain, 'orders': invoice_domain, 'draft_invoices': draft_domain, 'pos_orders': pos_domain, 'customers': [('id', 'in', customer_ids.ids)]},
        }
