# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models

class PurchaseSupplierPerformanceReport(models.TransientModel):
    _name = 'pt.purchase.supp'
    _description = 'Purchase Supplier Performance Report'

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
        supplier_stats = defaultdict(lambda: {'supplier': '', 'order_count': 0, 'amount_total': 0.0, 'receipt_count': 0, 'qty_received': 0.0, 'qty_ordered': 0.0, 'receipt_rate': 0.0, 'avg_delay': 0.0, 'delay_total': 0.0, 'delay_count': 0})
        details = []
        total_amount = 0.0
        total_receipts = 0
        total_delay = 0.0
        total_delay_count = 0
        for po in purchase_orders:
            supplier = po.partner_id.display_name or '-'
            stat = supplier_stats[supplier]
            stat['supplier'] = supplier
            stat['order_count'] += 1
            stat['amount_total'] += po.amount_total
            total_amount += po.amount_total
            ordered_qty = sum(po.order_line.mapped('product_qty'))
            received_qty = sum(po.order_line.mapped('qty_received'))
            stat['qty_ordered'] += ordered_qty
            stat['qty_received'] += received_qty
            pickings = po.picking_ids.filtered(lambda p: p.state == 'done')
            stat['receipt_count'] += len(pickings)
            total_receipts += len(pickings)
            for picking in pickings:
                if po.date_order and picking.date_done:
                    delay = (picking.date_done.date() - po.date_order.date()).days
                    stat['delay_total'] += delay
                    stat['delay_count'] += 1
                    total_delay += delay
                    total_delay_count += 1
                    details.append({'supplier': supplier, 'order': po.name, 'order_date': po.date_order, 'receipt_date': picking.date_done, 'amount': po.amount_total, 'qty_received': received_qty, 'delay': delay})
        for stat in supplier_stats.values():
            if stat['qty_ordered']:
                stat['receipt_rate'] = stat['qty_received'] / stat['qty_ordered'] * 100
            if stat['delay_count']:
                stat['avg_delay'] = stat['delay_total'] / stat['delay_count']
        supplier_list = sorted(supplier_stats.values(), key=lambda x: x['amount_total'], reverse=True)
        top_amount = sorted(supplier_stats.values(), key=lambda x: x['amount_total'], reverse=True)[:10]
        top_receipt = sorted(supplier_stats.values(), key=lambda x: x['receipt_rate'], reverse=True)[:10]
        kpi = {'supplier_count': len(supplier_stats), 'order_count': len(purchase_orders), 'total_amount': total_amount, 'receipt_count': total_receipts, 'receipt_rate': sum((s['receipt_rate'] for s in supplier_stats.values())) / len(supplier_stats) if supplier_stats else 0, 'avg_delay': total_delay / total_delay_count if total_delay_count else 0}
        return {'kpi': kpi, 'supplier_analysis': supplier_list, 'top_amount': top_amount, 'top_receipt': top_receipt, 'details': details}
