# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, models

class PrimetechPurchaseAnalysisReport(models.AbstractModel):
    _name = 'primetech.purchase.analysis.report'
    _description = 'Primetech Purchase Analysis Report'

    @api.model
    def _get_domain(self, filters):
        domain = []
        company_id = filters.get('company_id')
        supplier_ids = filters.get('supplier_ids')
        state = filters.get('state')
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        if company_id:
            domain.append(('company_id', '=', company_id))
        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))
        if state and state != 'all':
            if state == 'purchase':
                domain.append(('state', 'in', ['purchase', 'done']))
            else:
                domain.append(('state', '=', state))
        if date_from:
            domain.append(('date_order', '>=', f'{date_from} 00:00:00'))
        if date_to:
            domain.append(('date_order', '<=', f'{date_to} 23:59:59'))
        return domain

    @api.model
    def get_report_data(self, filters):
        PurchaseOrder = self.env['purchase.order']
        orders = PurchaseOrder.search(self._get_domain(filters), order='date_order desc')
        purchase_count = len(orders)
        supplier_count = len(orders.mapped('partner_id'))
        product_count = len(orders.mapped('order_line.product_id'))
        total_ht = sum(orders.mapped('amount_untaxed'))
        total_tax = sum(orders.mapped('amount_tax'))
        total_ttc = sum(orders.mapped('amount_total'))
        average_order = total_ttc / purchase_count if purchase_count else 0.0
        suppliers = []
        for supplier in orders.mapped('partner_id'):
            supplier_orders = orders.filtered(lambda o: o.partner_id.id == supplier.id)
            suppliers.append({'name': supplier.name, 'count': len(supplier_orders), 'amount': sum(supplier_orders.mapped('amount_total'))})
        top_suppliers = sorted(suppliers, key=lambda x: x['amount'], reverse=True)[:10]
        products = defaultdict(lambda: {'name': '', 'qty': 0, 'amount': 0})
        for order in orders:
            for line in order.order_line:
                product = line.product_id
                products[product.id]['name'] = product.display_name
                products[product.id]['qty'] += line.product_qty
                products[product.id]['amount'] += line.price_subtotal
        top_products = sorted(products.values(), key=lambda x: x['amount'], reverse=True)[:10]
        categories = defaultdict(float)
        for order in orders:
            for line in order.order_line:
                category = line.product_id.categ_id.display_name or 'Sans catégorie'
                categories[category] += line.price_subtotal
        expenses_by_category = [{'category': category, 'amount': amount} for category, amount in categories.items()]
        monthly = defaultdict(float)
        for order in orders:
            if not order.date_order:
                continue
            key = order.date_order.strftime('%Y-%m')
            monthly[key] += order.amount_total
        monthly_evolution = [{'period': period, 'amount': amount} for period, amount in sorted(monthly.items())]
        purchase_lines = []
        for order in orders:
            for line in order.order_line:
                purchase_lines.append({'date': order.date_order, 'order': order.name, 'supplier': order.partner_id.name, 'product': line.product_id.display_name, 'qty': line.product_qty, 'price_unit': line.price_unit, 'subtotal': line.price_subtotal, 'tax': line.price_tax, 'total': line.price_total, 'state': order.state})
        return {'purchase_count': purchase_count, 'supplier_count': supplier_count, 'product_count': product_count, 'total_ht': total_ht, 'total_tax': total_tax, 'total_ttc': total_ttc, 'average_order': average_order, 'top_suppliers': top_suppliers, 'top_products': top_products, 'expenses_by_category': expenses_by_category, 'monthly_evolution': monthly_evolution, 'purchase_lines': purchase_lines}
