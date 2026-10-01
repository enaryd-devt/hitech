# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import fields, models

class PurchaseReceiptReport(models.TransientModel):
    _name = 'pt.purchase.recv'
    _description = 'Purchase Receipts Report'

    def get_report_data(self, filters):
        domain = [('picking_type_code', '=', 'incoming')]
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        company_id = filters.get('company_id')
        supplier_ids = filters.get('supplier_ids')
        state = filters.get('state')
        if date_from:
            domain.append(('scheduled_date', '>=', date_from))
        if date_to:
            domain.append(('scheduled_date', '<=', date_to))
        if company_id:
            domain.append(('company_id', '=', company_id))
        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))
        if state and state != 'all':
            domain.append(('state', '=', state))
        receipts = self.env['stock.picking'].search(domain, order='scheduled_date desc')
        supplier_analysis = defaultdict(lambda: {'count': 0, 'qty': 0})
        product_analysis = defaultdict(float)
        state_analysis = defaultdict(int)
        total_expected_qty = 0
        total_received_qty = 0
        details = []
        for receipt in receipts:
            state_analysis[receipt.state] += 1
            supplier_name = receipt.partner_id.display_name or '-'
            receipt_qty = sum(receipt.move_ids_without_package.mapped('quantity'))
            received_qty = sum(receipt.move_ids_without_package.mapped('quantity'))
            total_expected_qty += receipt_qty
            total_received_qty += received_qty
            supplier_analysis[supplier_name]['count'] += 1
            supplier_analysis[supplier_name]['qty'] += received_qty
            for move in receipt.move_ids_without_package:
                product_analysis[move.product_id.display_name] += move.quantity
                details.append({'reference': receipt.name, 'date': receipt.scheduled_date, 'supplier': supplier_name, 'origin': receipt.origin or '-', 'product': move.product_id.display_name, 'qty_expected': move.quantity, 'qty_received': move.quantity, 'state': dict(receipt._fields['state'].selection).get(receipt.state, receipt.state)})
        kpi = {'receipt_count': len(receipts), 'supplier_count': len(receipts.mapped('partner_id')), 'product_count': len(receipts.mapped('move_ids_without_package.product_id')), 'done_count': len(receipts.filtered(lambda r: r.state == 'done')), 'waiting_count': len(receipts.filtered(lambda r: r.state in ('waiting', 'assigned', 'confirmed'))), 'cancel_count': len(receipts.filtered(lambda r: r.state == 'cancel')), 'total_expected_qty': total_expected_qty, 'total_received_qty': total_received_qty}
        return {'kpi': kpi, 'supplier_analysis': dict(supplier_analysis), 'product_analysis': dict(sorted(product_analysis.items(), key=lambda x: x[1], reverse=True)), 'state_analysis': dict(state_analysis), 'details': details}
