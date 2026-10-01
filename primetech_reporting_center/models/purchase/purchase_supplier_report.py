# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, models

class PrimetechPurchaseSupplierReport(models.AbstractModel):
    _name = 'primetech.purchase.supplier.report'
    _description = 'Purchase By Supplier Report'

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
        PurchaseOrder = self.env['purchase.order']
        orders = PurchaseOrder.search(self._get_domain(filters))
        lines = defaultdict(lambda: {'supplier': '', 'product': '', 'purchase_count': 0, 'qty': 0.0, 'amount_ht': 0.0, 'amount_tax': 0.0, 'amount_ttc': 0.0, 'last_order': False})
        total_ht = 0.0
        total_tax = 0.0
        total_ttc = 0.0
        suppliers = set()
        products = set()
        for order in orders:
            suppliers.add(order.partner_id.id)
            for line in order.order_line:
                products.add(line.product_id.id)
                key = (order.partner_id.id, line.product_id.id)
                lines[key]['supplier'] = order.partner_id.display_name
                lines[key]['product'] = line.product_id.display_name
                lines[key]['purchase_count'] += 1
                lines[key]['qty'] += line.product_qty
                lines[key]['amount_ht'] += line.price_subtotal
                lines[key]['amount_tax'] += line.price_tax
                lines[key]['amount_ttc'] += line.price_total
                if not lines[key]['last_order'] or order.date_order > lines[key]['last_order']:
                    lines[key]['last_order'] = order.date_order
                total_ht += line.price_subtotal
                total_tax += line.price_tax
                total_ttc += line.price_total
        report_lines = sorted(lines.values(), key=lambda x: (x['supplier'], -x['amount_ttc']))
        return {'supplier_count': len(suppliers), 'product_count': len(products), 'purchase_count': len(orders), 'total_ht': total_ht, 'total_tax': total_tax, 'total_ttc': total_ttc, 'lines': report_lines}

    def get_report_data(self, filters):
        return self._get_report_data(filters)
