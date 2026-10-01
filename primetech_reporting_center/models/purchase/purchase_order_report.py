# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import fields, models

class PurchaseOrderReport(models.TransientModel):
    _name = 'pt.purchase.order'
    _description = 'Purchase Orders Report'

    def get_report_data(self, filters):
        domain = []
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        company_id = filters.get('company_id')
        supplier_ids = filters.get('supplier_ids')
        user_ids = filters.get('user_ids')
        state = filters.get('state')
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if company_id:
            domain.append(('company_id', '=', company_id))
        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))
        if user_ids:
            domain.append(('user_id', 'in', user_ids))
        if state and state != 'all':
            domain.append(('state', '=', state))
        orders = self.env['purchase.order'].search(domain, order='date_order desc')
        total_amount = sum(orders.mapped('amount_total'))
        total_untaxed = sum(orders.mapped('amount_untaxed'))
        total_tax = sum(orders.mapped('amount_tax'))
        supplier_count = len(orders.mapped('partner_id'))
        product_count = len(orders.mapped('order_line.product_id'))
        confirmed_count = len(orders.filtered(lambda r: r.state in ('purchase', 'done')))
        draft_count = len(orders.filtered(lambda r: r.state in ('draft', 'sent')))
        cancelled_count = len(orders.filtered(lambda r: r.state == 'cancel'))
        avg_amount = total_amount / len(orders) if orders else 0.0
        supplier_analysis = defaultdict(float)
        buyer_analysis = defaultdict(float)
        state_analysis = defaultdict(int)
        monthly_analysis = defaultdict(float)
        details = []
        for order in orders:
            supplier_analysis[order.partner_id.display_name] += order.amount_total
            buyer_analysis[order.user_id.name or '-'] += order.amount_total
            state_analysis[order.state] += 1
            month_key = fields.Date.to_date(order.date_order).strftime('%Y-%m')
            monthly_analysis[month_key] += order.amount_total
            details.append({'name': order.name, 'date': order.date_order, 'supplier': order.partner_id.display_name, 'buyer': order.user_id.name or '-', 'company': order.company_id.name, 'untaxed': order.amount_untaxed, 'tax': order.amount_tax, 'total': order.amount_total, 'state': dict(order._fields['state'].selection).get(order.state, order.state)})
        return {'kpi': {'order_count': len(orders), 'total_amount': total_amount, 'total_untaxed': total_untaxed, 'total_tax': total_tax, 'avg_amount': avg_amount, 'supplier_count': supplier_count, 'product_count': product_count, 'confirmed_count': confirmed_count, 'draft_count': draft_count, 'cancelled_count': cancelled_count}, 'supplier_analysis': dict(sorted(supplier_analysis.items(), key=lambda x: x[1], reverse=True)), 'buyer_analysis': dict(sorted(buyer_analysis.items(), key=lambda x: x[1], reverse=True)), 'state_analysis': dict(state_analysis), 'monthly_analysis': dict(sorted(monthly_analysis.items())), 'details': details}
