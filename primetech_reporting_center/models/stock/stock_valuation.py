# -*- coding: utf-8 -*-
from odoo import api
from odoo import models

class StockValuationReport(models.AbstractModel):
    _name = 'pt.stock.valuation'
    _description = 'PrimeTech Stock Valuation Report'

    @api.model
    def get_report_data(self, filters):
        Product = self.env['product.product']
        Quant = self.env['stock.quant']
        domain = []
        if filters.get('product_ids'):
            domain.append(('id', 'in', filters['product_ids']))
        if filters.get('category_ids'):
            domain.append(('categ_id', 'child_of', filters['category_ids']))
        if filters.get('supplier_ids'):
            domain.append(('product_tmpl_id.seller_ids.partner_id', 'in', filters['supplier_ids']))
        products = Product.search(domain, order='name')
        total_products = 0
        total_qty = 0.0
        total_value = 0.0
        total_cost = 0.0
        top_product = ''
        top_product_value = 0.0
        lines = []
        for product in products:
            supplier_name = product.product_tmpl_id.seller_ids[:1].partner_id.name or 'Sans fournisseur'
            product_name = product.display_name
            quant_domain = [('product_id', '=', product.id), ('location_id.usage', '=', 'internal')]
            if filters.get('location_ids'):
                quant_domain.append(('location_id', 'in', filters['location_ids']))
            quants = Quant.search(quant_domain)
            qty = sum(quants.mapped('quantity'))
            if filters.get('only_available') and qty <= 0:
                continue
            cost_price = product.product_tmpl_id.standard_price
            stock_value = qty * cost_price
            total_products += 1
            total_qty += qty
            total_value += stock_value
            total_cost += cost_price
            if stock_value > top_product_value:
                top_product_value = stock_value
                top_product = product.name
            lines.append({'product_id': product.id, 'product_name': product_name, 'supplier_name': supplier_name, 'default_code': product.default_code or '', 'category': product.categ_id.display_name or '', 'quantity': round(qty, 2), 'cost_price': round(cost_price, 2), 'stock_value': round(stock_value, 2)})
        lines = sorted(lines, key=lambda x: (x['supplier_name'], -x['stock_value']) if filters.get('group_by_supplier') else -x['stock_value'])
        return {'kpi': {'products_count': total_products, 'total_qty': round(total_qty, 2), 'stock_value': round(total_value, 2), 'average_cost': round(total_cost / total_products if total_products else 0, 2), 'top_product': top_product, 'top_product_value': round(top_product_value, 2)}, 'lines': lines}
