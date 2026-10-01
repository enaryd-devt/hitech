# -*- coding: utf-8 -*-
from odoo import api
from odoo import models

class StockInventoryReport(models.AbstractModel):
    _name = 'pt.stock.inventory'
    _description = 'PrimeTech Stock Inventory'

    @api.model
    def get_report_data(self, filters):
        Quant = self.env['stock.quant']
        quant_domain = [('location_id.usage', '=', 'internal')]
        if filters.get('product_ids'):
            quant_domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('category_ids'):
            quant_domain.append(('product_id.categ_id', 'child_of', filters['category_ids']))
        if filters.get('location_ids'):
            quant_domain.append(('location_id', 'in', filters['location_ids']))
        if filters.get('lot_ids'):
            quant_domain.append(('lot_id', 'in', filters['lot_ids']))
        if filters.get('supplier_ids'):
            quant_domain.append(('product_id.product_tmpl_id.seller_ids.partner_id', 'in', filters['supplier_ids']))
        quants = Quant.search(quant_domain)
        quants = quants.sorted(key=lambda q: ((q.location_id.display_name or '').lower(), (q.product_id.categ_id.name or '').lower(), (q.product_id.name or '').lower(), (q.lot_id.name or '').lower()))
        products_count = 0
        lots_count = 0
        total_qty = 0.0
        out_of_stock_products = 0
        out_of_stock_lots = 0
        negative_stock_products = 0
        inventory = {}
        product_tracker = {}
        for quant in quants:
            product = quant.product_id
            supplier_name = product.product_tmpl_id.seller_ids[:1].partner_id.name or 'Sans fournisseur'
            qty_available = quant.quantity
            qty_reserved = quant.reserved_quantity
            lot = quant.lot_id
            has_lot = bool(lot)
            if filters.get('only_with_lot') and (not has_lot):
                continue
            if filters.get('only_without_lot') and has_lot:
                continue
            if filters.get('only_out_of_stock') and qty_available > 0:
                continue
            if filters.get('only_out_of_stock_lots') and has_lot and (qty_available > 0):
                continue
            if filters.get('only_negative_stock') and qty_available >= 0:
                continue
            total_qty += qty_available
            if qty_available < 0:
                negative_stock_products += 1
            if qty_available <= 0:
                out_of_stock_lots += 1
            if has_lot:
                lots_count += 1
            warehouse = self.env['stock.warehouse'].search([('view_location_id', 'parent_of', quant.location_id.id)], limit=1)
            warehouse_name = warehouse.name if warehouse else 'Sans Entrepôt'
            location_name = quant.location_id.display_name or quant.location_id.name
            category_name = product.categ_id.display_name or 'Sans Catégorie'
            lot_name = lot.name if lot else 'SANS LOT'
            product_key = (warehouse_name, location_name, category_name, supplier_name if filters.get('group_by_supplier') else '', product.id)
            if product_key not in product_tracker:
                product_tracker[product_key] = 0
                products_count += 1
            product_tracker[product_key] += 1
            first_line = product_tracker[product_key] == 1
            inventory.setdefault(warehouse_name, {})
            inventory[warehouse_name].setdefault(location_name, {})
            inventory[warehouse_name][location_name].setdefault(category_name, [])
            product_name = product.name
            inventory[warehouse_name][location_name][category_name].append({'product_id': product.id, 'product_name': product_name, 'default_code': product.default_code or '', 'lot_name': lot_name, 'qty_available': round(qty_available, 2), 'qty_reserved': round(qty_reserved, 2), 'first_line': first_line})
        product_totals = {}
        for warehouse_data in inventory.values():
            for location_data in warehouse_data.values():
                for category_data in location_data.values():
                    for line in category_data:
                        product_name = line['product_name']
                        if product_name not in product_totals:
                            product_totals[product_name] = 0
                        product_totals[product_name] += line['qty_available']
        for qty in product_totals.values():
            if qty <= 0:
                out_of_stock_products += 1
        warehouses_count = len(inventory)
        locations_count = 0
        for warehouse_data in inventory.values():
            locations_count += len(warehouse_data)
        categories_count = 0
        for warehouse_data in inventory.values():
            for location_data in warehouse_data.values():
                categories_count += len(location_data)
        return {'kpi': {'products_count': products_count, 'lots_count': lots_count, 'warehouses_count': warehouses_count, 'locations_count': locations_count, 'categories_count': categories_count, 'total_qty': round(total_qty, 2), 'out_of_stock_products': out_of_stock_products, 'out_of_stock_lots': out_of_stock_lots, 'negative_stock_products': negative_stock_products}, 'inventory': inventory}
