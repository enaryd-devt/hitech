# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

from ..date_range import DashboardDateRange


class StockDashboard(models.AbstractModel):
    _name = 'pt.stock.dashboard'
    _description = 'Stock Dashboard Service'

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        Product = self.env['product.product']
        Quant = self.env['stock.quant']
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']
        Location = self.env['stock.location']

        today = fields.Date.today()
        period, start, end = DashboardDateRange.resolve(filters, today)
        start_value = fields.Date.to_string(start)
        end_value = fields.Date.to_string(end)
        end_exclusive_value = fields.Date.to_string(end + timedelta(days=1))
        previous_start, _previous_end = DashboardDateRange.previous_bounds(start, end)
        previous_start_value = fields.Date.to_string(previous_start)
        settings = self.env['primetech.reporting.settings'].get_values()
        min_qty = settings['stock_min_alert_threshold']
        max_qty = settings['stock_overstock_threshold']

        Warehouse = self.env['stock.warehouse']
        warehouse_options = Warehouse.search([], order='name')
        try:
            selected_warehouse_id = int(filters.get('warehouse_id') or 0)
        except (TypeError, ValueError):
            selected_warehouse_id = 0
        selected_warehouse = Warehouse.browse(selected_warehouse_id).exists()
        picking_warehouse_domain = [('picking_type_id.warehouse_id', '=', selected_warehouse.id)] if selected_warehouse else []

        internal_location_domain = [('usage', '=', 'internal')]
        if selected_warehouse and selected_warehouse.view_location_id:
            internal_location_domain.append(('id', 'child_of', selected_warehouse.view_location_id.id))
        internal_locations = Location.search(internal_location_domain)
        internal_quants = Quant.search([('location_id', 'child_of', internal_locations.ids)]) if internal_locations else Quant.browse()
        products = internal_quants.mapped('product_id')
        product_domain = [('id', 'in', products.ids)]
        picking_domain = [('create_date', '>=', start_value), ('create_date', '<', end_exclusive_value)] + picking_warehouse_domain
        move_domain = [('state', '=', 'done'), ('date', '>=', start_value), ('date', '<', end_exclusive_value)] + picking_warehouse_domain
        moves = Move.search(move_domain)
        pickings = Picking.search(picking_domain)

        def reserved_qty(quant):
            return quant.reserved_quantity if 'reserved_quantity' in quant._fields else 0.0

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        product_stock = {}
        for quant in internal_quants:
            item = product_stock.setdefault(quant.product_id.id, {
                'product': quant.product_id,
                'qty': 0.0,
                'reserved': 0.0,
                'value': 0.0,
                'location': quant.location_id.display_name,
            })
            item['qty'] += quant.quantity
            item['reserved'] += reserved_qty(quant)
            item['value'] += quant.quantity * quant.product_id.standard_price

        stock_qty = round(sum(item['qty'] for item in product_stock.values()), 2)
        reserved_total = round(sum(item['reserved'] for item in product_stock.values()), 2)
        available_qty = round(stock_qty - reserved_total, 2)
        stock_value = round(sum(item['value'] for item in product_stock.values()), 2)
        stockout_items = [item for item in product_stock.values() if item['qty'] <= 0]
        below_min_items = [item for item in product_stock.values() if item['qty'] < min_qty]
        overstock_items = [item for item in product_stock.values() if item['qty'] > max_qty]

        outgoing_moves = moves.filtered(lambda move: move.picking_type_id.code == 'outgoing')
        outgoing_qty = sum(outgoing_moves.mapped('product_uom_qty'))
        period_days = max((end - start).days + 1, 1)
        average_daily_outgoing = outgoing_qty / period_days if period_days else 0.0
        coverage_days = round(available_qty / average_daily_outgoing, 1) if average_daily_outgoing else 0.0
        average_stock_qty = max((stock_qty + available_qty) / 2, 1)
        rotation = round(outgoing_qty / average_stock_qty, 2) if outgoing_qty else 0.0

        previous_moves = Move.search([('state', '=', 'done'), ('date', '>=', previous_start_value), ('date', '<', start_value)] + picking_warehouse_domain)
        previous_outgoing_qty = sum(previous_moves.filtered(lambda move: move.picking_type_id.code == 'outgoing').mapped('product_uom_qty'))
        previous_available_qty = max(available_qty - (sum(moves.filtered(lambda move: move.picking_type_id.code == 'incoming').mapped('product_uom_qty')) - outgoing_qty), 0.0)
        previous_stock_value = stock_value if not products else round(previous_available_qty * (stock_value / max(stock_qty, 1)), 2)
        previous_stockout = max(len(stockout_items) - 1, 0)
        previous_below_min = max(len(below_min_items) - 1, 0)
        previous_overstock = max(len(overstock_items) - 1, 0)
        previous_daily_outgoing = previous_outgoing_qty / period_days if period_days else 0.0
        previous_coverage = round(previous_available_qty / previous_daily_outgoing, 1) if previous_daily_outgoing else 0.0
        previous_rotation = round(previous_outgoing_qty / max(previous_available_qty, 1), 2) if previous_outgoing_qty else 0.0

        warehouses = []
        for location in internal_locations[:5]:
            location_quants = internal_quants.filtered(lambda quant: quant.location_id.id == location.id)
            value = round(sum(quant.quantity * quant.product_id.standard_price for quant in location_quants), 2)
            qty = round(sum(location_quants.mapped('quantity')), 2)
            reserved = round(sum(reserved_qty(quant) for quant in location_quants), 2)
            inbound = Picking.search_count([('location_dest_id', 'child_of', location.id), ('state', 'not in', ['done', 'cancel'])])
            outbound = Picking.search_count([('location_id', 'child_of', location.id), ('state', 'not in', ['done', 'cancel'])])
            latest_move = Move.search(['|', ('location_id', 'child_of', location.id), ('location_dest_id', 'child_of', location.id)], order='date desc', limit=1)
            warehouses.append({'id': location.id, 'name': location.display_name, 'value': value, 'available': qty - reserved, 'reserved': reserved, 'incoming': inbound, 'outgoing': outbound, 'latest_move': fields.Date.to_string(latest_move.date.date()) if latest_move and latest_move.date else ''})

        period_moves = []
        step = max((period_days + 7) // 8, 1)
        day = start
        while day <= end:
            next_day = min(day + timedelta(days=step), end + timedelta(days=1))
            period_moves.append({
                'label': day.strftime('%d/%m'),
                'incoming': Move.search_count([('state', '=', 'done'), ('date', '>=', fields.Date.to_string(day)), ('date', '<', fields.Date.to_string(next_day)), ('picking_type_id.code', '=', 'incoming')] + picking_warehouse_domain),
                'outgoing': Move.search_count([('state', '=', 'done'), ('date', '>=', fields.Date.to_string(day)), ('date', '<', fields.Date.to_string(next_day)), ('picking_type_id.code', '=', 'outgoing')] + picking_warehouse_domain),
                'internal': Move.search_count([('state', '=', 'done'), ('date', '>=', fields.Date.to_string(day)), ('date', '<', fields.Date.to_string(next_day)), ('picking_type_id.code', '=', 'internal')] + picking_warehouse_domain),
            })
            day = next_day

        shortage_products = []
        for item in stockout_items[:5]:
            product = item['product']
            shortage_products.append({'id': product.id, 'name': product.display_name, 'reference': product.default_code or '-', 'location': item['location'], 'qty': abs(round(item['qty'], 2))})

        replenishments = []
        for item in below_min_items[:5]:
            product = item['product']
            suggested = max_qty - item['qty'] if item['qty'] < min_qty else 0.0
            replenishments.append({'id': product.id, 'product_id': product.id, 'product': product.display_name, 'location': item['location'], 'qty': round(suggested, 2), 'priority': 'Haute' if item['qty'] <= 0 else 'Moyenne', 'status': 'À approuver'})

        below_min_product_ids = [item['product'].id for item in below_min_items]
        overstock_product_ids = [item['product'].id for item in overstock_items]

        alerts = {
            'stockout': len(stockout_items),
            'below_min': len(below_min_items),
            'overstock': len(overstock_items),
            'late_replenishments': Picking.search_count(picking_domain + [('scheduled_date', '<', fields.Date.to_string(today)), ('state', 'not in', ['done', 'cancel'])]),
            'soon_expiring_lots': 0,
        }

        # Presentation data for the visual stock overview. Picking types are
        # deliberately read dynamically so new warehouses and operations appear
        # in the dashboard without a code change.
        pending_states = ['draft', 'waiting', 'confirmed', 'assigned']
        type_icons = {'incoming': 'fa-sign-in', 'outgoing': 'fa-truck', 'internal': 'fa-exchange', 'mrp_operation': 'fa-cogs'}
        type_tones = {'incoming': 'blue', 'outgoing': 'violet', 'internal': 'orange', 'mrp_operation': 'green'}
        operation_cards = []
        operation_groups = {}
        picking_type_domain = [('warehouse_id', '=', selected_warehouse.id)] if selected_warehouse else []
        for picking_type in self.env['stock.picking.type'].search(picking_type_domain, order='sequence, name'):
            operation_domain = picking_domain + [('picking_type_id', '=', picking_type.id), ('state', 'in', pending_states)]
            late_domain = operation_domain + [('scheduled_date', '<', fields.Datetime.now())]
            card = {
                'id': picking_type.id,
                'name': picking_type.name,
                'code': picking_type.code,
                'icon': type_icons.get(picking_type.code, 'fa-cube'),
                'tone': type_tones.get(picking_type.code, 'blue'),
                'pending': Picking.search_count(operation_domain),
                'late': Picking.search_count(late_domain),
                'domain': operation_domain,
            }
            operation_cards.append(card)
            warehouse = picking_type.warehouse_id
            group_key = warehouse.id or 0
            group = operation_groups.setdefault(group_key, {
                'id': warehouse.id or False,
                'name': warehouse.display_name if warehouse else 'Autres opérations',
                'cards': [],
                'domain': [('picking_type_id.warehouse_id', '=', warehouse.id)] if warehouse else [('picking_type_id', '=', picking_type.id)],
            })
            group['cards'].append(card)

        recent_moves = []
        for move in moves.sorted(lambda item: item.date or fields.Datetime.now(), reverse=True)[:8]:
            recent_moves.append({
                'id': move.id,
                'date': fields.Datetime.to_string(move.date) if move.date else '',
                'reference': move.reference or move.picking_id.name or '-',
                'product': move.product_id.display_name,
                'quantity': round(move.quantity or move.product_uom_qty, 2),
                'operation': move.picking_type_id.name or 'Mouvement',
                'type': move.picking_type_id.code or 'internal',
            })

        category_values = {}
        category_quantities = {}
        category_ids = {}
        for item in product_stock.values():
            category_name = item['product'].categ_id.display_name or 'Sans catégorie'
            category_ids[category_name] = item['product'].categ_id.id
            category_values[category_name] = category_values.get(category_name, 0.0) + item['value']
            category_quantities[category_name] = category_quantities.get(category_name, 0.0) + item['qty']
        category_names = sorted(category_values, key=category_values.get, reverse=True)[:6]
        max_category_value = max([category_values[name] for name in category_names] or [1.0])
        max_category_qty = max([category_quantities[name] for name in category_names] or [1.0])
        category_data = [{
            'name': name,
            'id': category_ids[name],
            'value': round(category_values[name], 2),
            'quantity': round(category_quantities[name], 2),
            'value_ratio': round(category_values[name] / max_category_value * 100, 2),
            'quantity_ratio': round(category_quantities[name] / max_category_qty * 100, 2),
        } for name in category_names]

        low_stock_items = sorted(below_min_items, key=lambda item: item['qty'])[:6]
        low_stock_products = [{
            'id': item['product'].id,
            'name': item['product'].display_name,
            'reference': item['product'].default_code or '',
            'available': round(item['qty'], 2),
            'minimum': min_qty,
            'suggested': round(max(max_qty - item['qty'], 0.0), 2),
            'image_url': '/web/image/product.product/%s/image_128' % item['product'].id,
            'level': 'critical' if item['qty'] <= 0 else 'warning',
        } for item in low_stock_items]

        return {
            'today': fields.Date.to_string(today), 'date_from': start_value, 'date_to': end_value, 'period': period, 'updated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M'),
            'stock_value': stock_value, 'previous_stock_value': previous_stock_value, 'stock_value_growth': growth(stock_value, previous_stock_value),
            'available_qty': available_qty, 'previous_available_qty': previous_available_qty, 'available_growth': growth(available_qty, previous_available_qty),
            'out_of_stock': len(stockout_items), 'previous_out_of_stock': previous_stockout, 'out_of_stock_growth': growth(len(stockout_items), previous_stockout),
            'below_min': len(below_min_items), 'previous_below_min': previous_below_min, 'below_min_growth': growth(len(below_min_items), previous_below_min),
            'overstock': len(overstock_items), 'previous_overstock': previous_overstock, 'overstock_growth': growth(len(overstock_items), previous_overstock),
            'coverage_days': coverage_days, 'previous_coverage_days': previous_coverage, 'coverage_growth': growth(coverage_days, previous_coverage),
            'rotation': rotation, 'previous_rotation': previous_rotation, 'rotation_growth': growth(rotation, previous_rotation),
            'warehouses': warehouses, 'period_moves': period_moves, 'shortage_products': shortage_products, 'replenishments': replenishments, 'alerts': alerts,
            'products_count': len(products), 'stock_qty': stock_qty, 'locations_count': len(internal_locations), 'pending_pickings': len(pickings),
            'below_min_product_ids': below_min_product_ids, 'overstock_product_ids': overstock_product_ids,
            'settings': settings,
            'warehouse_options': [{'id': warehouse.id, 'name': warehouse.display_name} for warehouse in warehouse_options],
            'selected_warehouse_id': selected_warehouse.id if selected_warehouse else False,
            'operation_cards': operation_cards,
            'operation_groups': list(operation_groups.values()),
            'recent_moves': recent_moves,
            'category_data': category_data,
            'low_stock_products': low_stock_products,
            'stock_levels': [
                {'label': 'Stock satisfaisant', 'value': max(len(products) - len(below_min_items), 0), 'tone': 'green'},
                {'label': 'Stock faible', 'value': len([item for item in below_min_items if item['qty'] > 0]), 'tone': 'orange'},
                {'label': 'Rupture de stock', 'value': len(stockout_items), 'tone': 'red'},
            ],
            'domains': {'products': product_domain, 'locations': internal_location_domain, 'pickings': picking_domain, 'moves': move_domain, 'orderpoints': [('id', 'in', below_min_product_ids)]},
        }

    # ------------------------------------------------------------
    # Centre de Commandement Logistique (Supply Chain Manager)
    # ------------------------------------------------------------
    @api.model
    def get_logistics_command_center(self):
        """Richer command center payload for stock managers."""
        Picking = self.env['stock.picking']
        Warehouse = self.env['stock.warehouse']
        Product = self.env['product.product']
        Quant = self.env['stock.quant']
        Move = self.env['stock.move']
        today = fields.Date.today()
        today_value = fields.Date.to_string(today)
        limit_date = today - timedelta(days=30)
        limit_value = fields.Date.to_string(limit_date)
        settings = self.env['primetech.reporting.settings'].get_values()
        min_qty = settings['stock_min_alert_threshold']
        max_qty = settings['stock_overstock_threshold']
        base_picking_domain = []
        base_product_domain = []
        internal_quants = Quant.search([('location_id.usage', '=', 'internal')])
        products = internal_quants.mapped('product_id') or Product.search([])

        product_stock = {}
        for quant in internal_quants:
            entry = product_stock.setdefault(quant.product_id.id, {'product': quant.product_id, 'qty': 0.0})
            entry['qty'] += quant.quantity
        stockout_items = [item for item in product_stock.values() if item['qty'] <= 0]
        below_min_items = [item for item in product_stock.values() if item['qty'] < min_qty]
        overstock_items = [item for item in product_stock.values() if item['qty'] > max_qty]
        stockout_ids = [item['product'].id for item in stockout_items]
        below_min_ids = [item['product'].id for item in below_min_items]
        overstock_ids = [item['product'].id for item in overstock_items]

        status_labels = {
            'draft': 'Brouillon', 'waiting': 'En attente', 'confirmed': 'À préparer',
            'assigned': 'Prêt', 'done': 'Terminé', 'cancel': 'Annulé',
        }
        transfers_by_state = [
            {'state': state, 'label': label, 'count': Picking.search_count([('state', '=', state)]), 'domain': [('state', '=', state)]}
            for state, label in status_labels.items()
        ]
        procurement_requests = [
            {'label': 'Demandes', 'count': Picking.search_count([('state', 'in', ('draft', 'waiting'))]), 'domain': [('state', 'in', ['draft', 'waiting'])]},
            {'label': 'À préparer', 'count': Picking.search_count([('state', '=', 'confirmed')]), 'domain': [('state', '=', 'confirmed')]},
            {'label': 'Prêtes', 'count': Picking.search_count([('state', '=', 'assigned')]), 'domain': [('state', '=', 'assigned')]},
            {'label': 'Entrées', 'count': Picking.search_count([('picking_type_id.code', '=', 'incoming'), ('state', 'not in', ['done', 'cancel'])]), 'domain': [('picking_type_id.code', '=', 'incoming'), ('state', 'not in', ['done', 'cancel'])]},
            {'label': 'Sorties', 'count': Picking.search_count([('picking_type_id.code', '=', 'outgoing'), ('state', 'not in', ['done', 'cancel'])]), 'domain': [('picking_type_id.code', '=', 'outgoing'), ('state', 'not in', ['done', 'cancel'])]},
            {'label': 'Internes', 'count': Picking.search_count([('picking_type_id.code', '=', 'internal'), ('state', 'not in', ['done', 'cancel'])]), 'domain': [('picking_type_id.code', '=', 'internal'), ('state', 'not in', ['done', 'cancel'])]},
        ]

        warehouse_load = []
        for warehouse in Warehouse.search([]):
            domain = [('picking_type_id.warehouse_id', '=', warehouse.id)]
            in_progress = Picking.search_count(domain + [('state', 'in', ('confirmed', 'assigned'))])
            waiting = Picking.search_count(domain + [('state', 'in', ('draft', 'waiting'))])
            completed = Picking.search_count(domain + [('state', '=', 'done'), ('date_done', '>=', limit_value)])
            warehouse_locations = warehouse.view_location_id and self.env['stock.location'].search([('id', 'child_of', warehouse.view_location_id.id)]) or self.env['stock.location']
            wh_quants = internal_quants.filtered(lambda q: q.location_id.id in warehouse_locations.ids)
            wh_stockouts = len([q for q in wh_quants if q.quantity <= 0])
            warehouse_load.append({'id': warehouse.id, 'name': warehouse.display_name, 'in_progress': in_progress, 'waiting': waiting, 'completed': completed, 'stockouts': wh_stockouts, 'domain': domain})

        done_pickings = Picking.search([('state', '=', 'done'), ('date_done', '>=', limit_value)])
        late_pickings = done_pickings.filtered(lambda p: p.scheduled_date and p.date_done and p.date_done > p.scheduled_date)
        prep_delays = [(p.date_done - p.scheduled_date).total_seconds() / 3600.0 for p in done_pickings if p.scheduled_date and p.date_done]
        avg_prep_delay_hours = round(sum(prep_delays) / len(prep_delays), 1) if prep_delays else 0
        open_recent = Picking.search_count([('state', 'not in', ('done', 'cancel')), ('create_date', '>=', limit_value)])
        total_recent = len(done_pickings) + open_recent
        service_rate = round(len(done_pickings) / total_recent * 100, 1) if total_recent else 0
        late_rate = round(len(late_pickings) / len(done_pickings) * 100, 1) if done_pickings else 0
        preparation_errors = Picking.search_count([('state', '=', 'cancel'), ('create_date', '>=', limit_value)])
        error_rate = round(preparation_errors / total_recent * 100, 1) if total_recent else 0
        late_open = Picking.search_count([('scheduled_date', '<', today_value), ('state', 'not in', ['done', 'cancel'])])

        customer_orders = [
            {'label': 'À préparer', 'count': Picking.search_count([('picking_type_id.code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'assigned'))]), 'domain': [('picking_type_id.code', '=', 'outgoing'), ('state', 'in', ['confirmed', 'assigned'])]},
            {'label': 'En attente', 'count': Picking.search_count([('picking_type_id.code', '=', 'outgoing'), ('state', 'in', ('draft', 'waiting'))]), 'domain': [('picking_type_id.code', '=', 'outgoing'), ('state', 'in', ['draft', 'waiting'])]},
            {'label': 'Livrées 30j', 'count': Picking.search_count([('picking_type_id.code', '=', 'outgoing'), ('state', '=', 'done'), ('date_done', '>=', limit_value)]), 'domain': [('picking_type_id.code', '=', 'outgoing'), ('state', '=', 'done'), ('date_done', '>=', limit_value)]},
        ]
        urgent_transfers = [
            {'id': picking.id, 'name': picking.name, 'origin': picking.origin or picking.picking_type_id.display_name, 'deadline': fields.Date.to_string(picking.scheduled_date.date()) if picking.scheduled_date else ''}
            for picking in Picking.search([('scheduled_date', '<=', today_value), ('state', 'not in', ['done', 'cancel'])], order='scheduled_date asc', limit=6)
        ]
        top_products_to_replenish = [
            {'id': item['product'].id, 'name': item['product'].display_name, 'qty': round(item['qty'], 2), 'suggested_qty': round(max_qty - item['qty'], 2)}
            for item in sorted(below_min_items, key=lambda x: x['qty'])[:6]
        ]
        carrier_workload = []
        for picking_type in self.env['stock.picking.type'].search([], limit=5):
            domain = [('picking_type_id', '=', picking_type.id), ('state', 'not in', ['done', 'cancel'])]
            carrier_workload.append({'name': picking_type.display_name, 'count': Picking.search_count(domain), 'domain': domain})

        fleet = {'vehicles': 0, 'drivers': 0}
        if 'fleet.vehicle' in self.env.registry:
            fleet['vehicles'] = self.env['fleet.vehicle'].search_count([])
        if 'hr.employee' in self.env.registry:
            fleet['drivers'] = self.env['hr.employee'].search_count([('job_title', 'ilike', 'chauffeur')])

        return {
            'today': today_value, 'limit_date': limit_value,
            'transfers_by_state': transfers_by_state,
            'procurement_requests': procurement_requests,
            'customer_orders': customer_orders,
            'fleet': fleet,
            'warehouse_load': warehouse_load,
            'urgent_transfers': urgent_transfers,
            'top_products_to_replenish': top_products_to_replenish,
            'carrier_workload': carrier_workload,
            'alert_product_ids': {'stockouts': stockout_ids, 'below_min': below_min_ids, 'overstock': overstock_ids},
            'alerts': {'stockouts': len(stockout_ids), 'below_min': len(below_min_ids), 'overstock': len(overstock_ids)},
            'kpis': {
                'to_prepare': Picking.search_count([('state', 'in', ['confirmed', 'assigned'])]),
                'late_transfers': late_open,
                'avg_prep_delay_hours': avg_prep_delay_hours,
                'service_rate': service_rate,
                'late_rate': late_rate,
                'delivery_delay_hours': avg_prep_delay_hours,
                'error_rate': error_rate,
                'completed_last_30_days': len(done_pickings),
            },
            'domains': {'pickings': base_picking_domain, 'products': base_product_domain, 'moves': [('state', '=', 'done'), ('date', '>=', limit_value)]},
        }
