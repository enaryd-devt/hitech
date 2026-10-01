# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api
from odoo import models

class StockMovementReport(models.AbstractModel):
    _name = 'pt.stock.movement'
    _description = 'PrimeTech Stock Movement Report'

    @api.model
    def get_report_data(self, filters):
        MoveLine = self.env['stock.move.line']
        domain = []
        if filters.get('date_from'):
            domain.append(('date', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('date', '<=', filters['date_to']))
        if filters.get('product_ids'):
            domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('category_ids'):
            domain.append(('product_id.categ_id', 'child_of', filters['category_ids']))
        if filters.get('lot_ids'):
            domain.append(('lot_id', 'in', filters['lot_ids']))
        if filters.get('supplier_ids'):
            domain.append(('move_id.partner_id', 'in', filters['supplier_ids']))
        if filters.get('validated_only'):
            domain.append(('state', '=', 'done'))
        move_lines = MoveLine.search(domain, order='\n                product_id,\n                date,\n                id\n            ')
        products_count = 0
        movements_count = len(move_lines)
        total_entries = 0.0
        total_outputs = 0.0
        total_entry_value = 0.0
        total_output_value = 0.0
        products = {}
        move_lines = move_lines.sorted(key=lambda l: ((l.product_id.name or '').lower(), l.date, l.id))
        for line in move_lines:
            product = line.product_id
            move = line.move_id
            partner_name = move.partner_id.name if move.partner_id else ''
            supplier_group = partner_name if line.location_id.usage == 'supplier' and partner_name else 'Autres mouvements'
            product_id = (supplier_group, product.id) if filters.get('group_by_supplier') else product.id
            if product_id not in products:
                products_count += 1
                products[product_id] = {'product_id': product.id, 'product_name': product.name, 'default_code': product.default_code or '', 'category_name': product.categ_id.name or '', 'uom_name': product.uom_id.name or '', 'cost': product.standard_price, 'lines': [], 'total_in': 0.0, 'total_out': 0.0, 'balance': 0.0, 'valuation': 0.0}
            product_data = products[product_id]
            qty = abs(line.quantity or line.qty_done or 0.0)
            lot_name = line.lot_id.name if line.lot_id else 'SANS LOT'
            source_usage = line.location_id.usage
            dest_usage = line.location_dest_id.usage
            lines_to_create = []
            if source_usage == 'supplier':
                lines_to_create.append({'movement_type': 'Entrée', 'qty_in': qty, 'qty_out': 0.0, 'source_name': partner_name or 'Fournisseur', 'destination_name': line.location_dest_id.complete_name})
            elif dest_usage == 'customer':
                lines_to_create.append({'movement_type': 'Sortie', 'qty_in': 0.0, 'qty_out': qty, 'source_name': line.location_id.complete_name, 'destination_name': partner_name or 'Client'})
            elif source_usage == 'inventory' or dest_usage == 'inventory':
                if source_usage == 'inventory':
                    lines_to_create.append({'movement_type': 'Ajustement +', 'qty_in': qty, 'qty_out': 0.0, 'source_name': 'Ajustement Inventaire', 'destination_name': line.location_dest_id.complete_name})
                else:
                    lines_to_create.append({'movement_type': 'Ajustement -', 'qty_in': 0.0, 'qty_out': qty, 'source_name': line.location_id.complete_name, 'destination_name': 'Ajustement Inventaire'})
            else:
                lines_to_create.append({'movement_type': 'Transfert Sortant', 'qty_in': 0.0, 'qty_out': qty, 'source_name': line.location_id.complete_name, 'destination_name': line.location_dest_id.complete_name})
                lines_to_create.append({'movement_type': 'Transfert Entrant', 'qty_in': qty, 'qty_out': 0.0, 'source_name': line.location_id.complete_name, 'destination_name': line.location_dest_id.complete_name})
            document_name = move.reference or move.origin or move.picking_id.name or move.name or ''
            for movement in lines_to_create:
                qty_in = movement['qty_in']
                qty_out = movement['qty_out']
                product_data['balance'] += qty_in
                product_data['balance'] -= qty_out
                balance = product_data['balance']
                cost = product.standard_price or 0.0
                valuation = balance * cost
                product_data['total_in'] += qty_in
                product_data['total_out'] += qty_out
                product_data['valuation'] = valuation
                total_entries += qty_in
                total_outputs += qty_out
                total_entry_value += qty_in * cost
                total_output_value += qty_out * cost
                product_data['lines'].append({'date': line.date, 'partner_name': partner_name, 'document': document_name, 'movement_type': movement['movement_type'], 'source_name': movement['source_name'], 'destination_name': movement['destination_name'], 'lot_name': lot_name, 'qty_in': qty_in, 'qty_out': qty_out, 'balance': balance, 'cost': cost, 'valuation': valuation, 'is_entry': qty_in > 0, 'is_output': qty_out > 0})
        products = dict(sorted(products.items(), key=lambda item: (item[1]['product_name'] or '').lower()))
        total_balance = sum((p['balance'] for p in products.values()))
        total_valuation = sum((p['valuation'] for p in products.values()))
        products_with_moves = len(products)
        lots_count = len({line['lot_name'] for product in products.values() for line in product['lines'] if line['lot_name'] != 'SANS LOT'})
        product_list = list(products.values())
        return {'kpi': {'products_count': products_count, 'movements_count': movements_count, 'lots_count': lots_count, 'total_entries': round(total_entries, 2), 'total_outputs': round(total_outputs, 2), 'total_balance': round(total_balance, 2), 'total_entry_value': round(total_entry_value, 2), 'total_output_value': round(total_output_value, 2), 'total_valuation': round(total_valuation, 2)}, 'products': product_list}
