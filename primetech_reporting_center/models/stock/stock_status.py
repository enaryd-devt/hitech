# -*- coding: utf-8 -*-
from odoo import api
from odoo import models

class StockStatusReport(models.AbstractModel):
    _name = 'pt.stock.status'
    _description = 'Stock Status Report'

    @api.model
    def get_report_data(self, filters):
        Product = self.env['product.product']
        Quant = self.env['stock.quant']
        Move = self.env['stock.move']
        domain = []
        if filters.get('product_ids'):
            domain.append(('id', 'in', filters['product_ids']))
        if filters.get('category_ids'):
            domain.append(('categ_id', 'child_of', filters['category_ids']))
        if filters.get('supplier_ids'):
            domain.append(('product_tmpl_id.seller_ids.partner_id', 'in', filters['supplier_ids']))
        products = Product.search(domain)
        total_products = 0
        total_qty = 0.0
        total_reserved = 0.0
        total_value = 0.0
        out_of_stock = 0
        lines = []
        for product in products:
            supplier_name = product.product_tmpl_id.seller_ids[:1].partner_id.name or 'Sans fournisseur'
            product_name = product.display_name
            quant_domain = [('product_id', '=', product.id), ('location_id.usage', '=', 'internal')]
            if filters.get('location_ids'):
                quant_domain.append(('location_id', 'in', filters['location_ids']))
            quants = Quant.search(quant_domain)
            qty = sum(quants.mapped('quantity'))
            reserved = sum(quants.mapped('reserved_quantity'))
            available_qty = qty - reserved
            if filters.get('only_available') and available_qty <= 0:
                continue
            if filters.get('only_out_of_stock') and qty > 0:
                continue
            cost_price = product.product_tmpl_id.standard_price
            sale_price = product.product_tmpl_id.list_price
            value = qty * cost_price
            total_products += 1
            total_qty += qty
            total_reserved += reserved
            total_value += value
            if qty <= 0:
                out_of_stock += 1
            last_move = Move.search([('product_id', '=', product.id), ('state', '=', 'done')], limit=1, order='date desc')
            incoming_qty = sum(Move.search([('product_id', '=', product.id), ('state', 'not in', ['done', 'cancel']), ('picking_type_id.code', '=', 'incoming')]).mapped('product_uom_qty'))
            outgoing_qty = sum(Move.search([('product_id', '=', product.id), ('state', 'not in', ['done', 'cancel']), ('picking_type_id.code', '=', 'outgoing')]).mapped('product_uom_qty'))
            locations = ', '.join(sorted(set(quants.mapped('location_id.display_name'))))
            locations = []
            for location in quants.mapped('location_id'):
                location_quants = quants.filtered(lambda q: q.location_id.id == location.id)
                location_qty = sum(location_quants.mapped('quantity'))
                locations.append(f'{location.display_name}:{location_qty:,.0f}')
            locations = '\n'.join(sorted(locations))
            if qty <= 0:
                stock_state = 'rupture'
            elif available_qty <= 10:
                stock_state = 'faible'
            else:
                stock_state = 'normal'
            lines.append({'product_id': product.id, 'product_name': product_name, 'supplier_name': supplier_name, 'default_code': product.default_code or '', 'category': product.categ_id.display_name or '', 'location': locations, 'available_qty': round(available_qty, 2), 'qty_on_hand': round(qty, 2), 'reserved_qty': round(reserved, 2), 'incoming_qty': round(incoming_qty, 2), 'outgoing_qty': round(outgoing_qty, 2), 'cost_price': round(cost_price, 2), 'sale_price': round(sale_price, 2), 'value': round(value, 2), 'last_move_date': last_move.date.strftime('%d/%m/%Y') if last_move else '', 'state': stock_state})
        lines = sorted(lines, key=lambda l: (l['supplier_name'], -l['value']) if filters.get('group_by_supplier') else -l['value'])
        return {'kpi': {'products_count': total_products, 'total_qty': round(total_qty, 2), 'reserved_qty': round(total_reserved, 2), 'stock_value': round(total_value, 2), 'out_of_stock': out_of_stock}, 'lines': lines}
