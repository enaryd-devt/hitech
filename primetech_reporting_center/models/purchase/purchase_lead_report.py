# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models

class PurchaseLeadReport(models.TransientModel):
    _name = 'pt.purchase.lead'
    _description = 'Purchase Lead Time Report'

    def get_report_data(self, filters):
        domain = []
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        company_id = filters.get('company_id')
        supplier_ids = filters.get('supplier_ids')
        state = filters.get('state')
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if company_id:
            domain.append(('company_id', '=', company_id))
        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))
        if state and state != 'all':
            domain.append(('state', '=', state))
        purchase_orders = self.env['purchase.order'].search(domain, order='date_order desc')
        details = []
        supplier_stats = defaultdict(lambda: {'supplier': '', 'order_count': 0, 'avg_delay': 0.0, 'min_delay': 0.0, 'max_delay': 0.0, 'delay_total': 0.0, 'delay_count': 0})
        delays = []
        late_orders = 0
        for po in purchase_orders:
            pickings = po.picking_ids.filtered(lambda p: p.state == 'done' and p.date_done)
            for picking in pickings:
                if not po.date_order:
                    continue
                delay = (picking.date_done.date() - po.date_order.date()).days
                supplier = po.partner_id.display_name or '-'
                stat = supplier_stats[supplier]
                stat['supplier'] = supplier
                stat['order_count'] += 1
                stat['delay_total'] += delay
                stat['delay_count'] += 1
                delays.append(delay)
                if delay > 30:
                    late_orders += 1
                details.append({'order': po.name, 'supplier': supplier, 'order_date': po.date_order, 'receipt_date': picking.date_done, 'delay': delay, 'amount': po.amount_total})
        for stat in supplier_stats.values():
            if stat['delay_count']:
                stat['avg_delay'] = stat['delay_total'] / stat['delay_count']
                supplier_delays = [d['delay'] for d in details if d['supplier'] == stat['supplier']]
                stat['min_delay'] = min(supplier_delays)
                stat['max_delay'] = max(supplier_delays)
        supplier_analysis = sorted(supplier_stats.values(), key=lambda x: x['avg_delay'])
        top_fast = sorted(supplier_stats.values(), key=lambda x: x['avg_delay'])[:10]
        top_slow = sorted(supplier_stats.values(), key=lambda x: x['avg_delay'], reverse=True)[:10]
        kpi = {'order_count': len(purchase_orders), 'receipt_count': len(details), 'avg_delay': sum(delays) / len(delays) if delays else 0, 'min_delay': min(delays) if delays else 0, 'max_delay': max(delays) if delays else 0, 'late_orders': late_orders}
        return {'kpi': kpi, 'supplier_analysis': supplier_analysis, 'top_fast': top_fast, 'top_slow': top_slow, 'details': details}
