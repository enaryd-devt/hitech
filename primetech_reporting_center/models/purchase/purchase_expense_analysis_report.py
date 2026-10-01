# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, models

class PrimetechPurchaseExpenseReport(models.AbstractModel):
    _name = 'primetech.purchase.expense.report'
    _description = 'Purchase Expense Report'

    @api.model
    def _get_domain(self, filters):
        domain = []
        if filters.get('date_from'):
            domain.append(('date_order', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('date_order', '<=', filters['date_to']))
        if filters.get('company_id'):
            domain.append(('company_id', '=', filters['company_id']))
        if filters.get('supplier_ids'):
            domain.append(('partner_id', 'in', filters['supplier_ids']))
        if filters.get('state') and filters['state'] != 'all':
            domain.append(('state', '=', filters['state']))
        return domain

    @api.model
    def _get_report_data(self, filters):
        orders = self.env['purchase.order'].search(self._get_domain(filters))
        total_ht = 0.0
        total_tax = 0.0
        total_ttc = 0.0
        categories = defaultdict(lambda: {'category': '', 'amount': 0.0, 'products': set()})
        suppliers = defaultdict(lambda: {'supplier': '', 'purchase_count': 0, 'amount_ht': 0.0, 'amount_ttc': 0.0})
        monthly = defaultdict(float)
        lines = []
        for order in orders:
            supplier = order.partner_id.display_name
            suppliers[supplier]['supplier'] = supplier
            suppliers[supplier]['purchase_count'] += 1
            suppliers[supplier]['amount_ht'] += order.amount_untaxed
            suppliers[supplier]['amount_ttc'] += order.amount_total
            total_ht += order.amount_untaxed
            total_tax += order.amount_tax
            total_ttc += order.amount_total
            if order.date_order:
                period = order.date_order.strftime('%Y-%m')
                monthly[period] += order.amount_total
            for line in order.order_line:
                category = line.product_id.categ_id.display_name or 'Sans catégorie'
                categories[category]['category'] = category
                categories[category]['amount'] += line.price_subtotal
                categories[category]['products'].add(line.product_id.id)
                lines.append({'date': order.date_order, 'supplier': supplier, 'category': category, 'product': line.product_id.display_name, 'qty': line.product_qty, 'amount': line.price_subtotal})
        categories_list = []
        for item in categories.values():
            categories_list.append({'category': item['category'], 'product_count': len(item['products']), 'amount': item['amount'], 'percent': item['amount'] * 100 / total_ht if total_ht else 0})
        categories_list = sorted(categories_list, key=lambda x: x['amount'], reverse=True)
        suppliers_list = sorted(suppliers.values(), key=lambda x: x['amount_ht'], reverse=True)
        monthly_list = [{'period': period, 'amount': amount} for period, amount in sorted(monthly.items())]
        return {'total_ht': total_ht, 'total_tax': total_tax, 'total_ttc': total_ttc, 'category_count': len(categories_list), 'supplier_count': len(suppliers_list), 'highest_category': categories_list[0]['category'] if categories_list else '-', 'highest_supplier': suppliers_list[0]['supplier'] if suppliers_list else '-', 'categories': categories_list, 'suppliers': suppliers_list, 'monthly': monthly_list, 'lines': lines}

    def get_report_data(self, filters):
        return self._get_report_data(filters)
