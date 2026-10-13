# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time

from odoo import api, fields, models


class CustomerDeliveryReport(models.AbstractModel):
    _name = 'pt.customer.delivery.report'
    _description = 'Rapport des produits déstockés et livrés'

    @api.model
    def get_report_data(self, filters):
        date_to = fields.Date.to_date(filters['date_to'])
        domain = [
            ('company_id', '=', filters['company_id']),
            ('state', '=', 'done'),
            ('location_dest_id.usage', '=', 'customer'),
            ('date', '>=', fields.Date.to_date(filters['date_from'])),
            ('date', '<=', fields.Datetime.to_string(datetime.combine(date_to, time.max))),
        ]
        if filters.get('warehouse_ids'):
            domain.append(('location_id.warehouse_id', 'in', filters['warehouse_ids']))
        if filters.get('category_ids'):
            domain.append(('product_id.categ_id', 'child_of', filters['category_ids']))
        if filters.get('product_ids'):
            domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('customer_ids'):
            domain.append(('move_id.partner_id', 'in', filters['customer_ids']))

        lines = self.env['stock.move.line'].search(domain, order='date, id')
        products = defaultdict(lambda: {'product': False, 'quantity': 0.0, 'stock_remaining': 0.0})
        deliveries = []
        warehouses = self.env['stock.warehouse'].browse(filters.get('warehouse_ids', []))
        stock_context = {'to_date': fields.Datetime.to_string(datetime.combine(date_to, time.max))}
        for line in lines:
            product = line.product_id
            customer = line.move_id.partner_id or line.picking_id.partner_id
            quantity = abs(line.quantity or line.qty_done or 0.0)
            if not products[product.id]['product']:
                products[product.id]['product'] = product
                if warehouses:
                    products[product.id]['stock_remaining'] = sum(
                        product.with_context(**stock_context, warehouse_id=warehouse.id).qty_available
                        for warehouse in warehouses
                    )
                else:
                    products[product.id]['stock_remaining'] = product.with_context(**stock_context).qty_available
            products[product.id]['quantity'] += quantity
            deliveries.append({
                'date': line.date,
                'document': line.picking_id.name or line.move_id.reference or line.move_id.origin or line.move_id.name,
                'customer': customer.name if customer else 'Client non renseigné',
                'product': product,
                'quantity': quantity,
                'uom': product.uom_id.name,
                'stock_remaining': products[product.id]['stock_remaining'],
            })
        summary = sorted(({
            'product': item['product'], 'quantity': item['quantity'], 'stock_remaining': item['stock_remaining'],
        } for item in products.values()), key=lambda item: (item['product'].display_name or '').lower())
        return {
            'lines': deliveries,
            'summary': summary,
            'warehouse_names': warehouses.mapped('display_name'),
            'kpi': {
                'delivery_count': len(lines),
                'product_count': len(products),
                'quantity': sum(item['quantity'] for item in products.values()),
            },
        }
