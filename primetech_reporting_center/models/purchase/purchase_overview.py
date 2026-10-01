# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import date, datetime, timedelta
from odoo import api, models

from ..date_range import DashboardDateRange


class PrimetechPurchaseOverview(models.AbstractModel):
    _name = 'primetech.purchase.overview'
    _description = 'Primetech Purchase Overview Dashboard'

    def _period_bounds(self, filters, today):
        return DashboardDateRange.resolve(filters, today)

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        today = date.today()
        period, start, end = self._period_bounds(filters, today)
        start_value = start.isoformat()
        end_value = end.isoformat()
        end_exclusive_value = (end + timedelta(days=1)).isoformat()
        previous_start, previous_end = DashboardDateRange.previous_bounds(start, end)
        previous_start_value = previous_start.isoformat()
        PurchaseOrder = self.env['purchase.order']
        AccountMove = self.env['account.move']
        StockPicking = self.env['stock.picking']
        order_domain = [('date_order', '>=', start_value), ('date_order', '<', end_exclusive_value)]
        confirmed_domain = order_domain + [('state', 'in', ['purchase', 'done'])]
        bill_domain = [('move_type', '=', 'in_invoice'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        receipt_domain = [('picking_type_code', '=', 'incoming'), ('scheduled_date', '>=', start_value), ('scheduled_date', '<', end_exclusive_value)]
        purchase_orders = PurchaseOrder.search(confirmed_domain)
        all_period_orders = PurchaseOrder.search(order_domain)
        vendor_bills = AccountMove.search(bill_domain)
        receipts = StockPicking.search(receipt_domain)
        previous_orders = PurchaseOrder.search([('date_order', '>=', previous_start_value), ('date_order', '<', start_value), ('state', 'in', ['purchase', 'done'])])
        previous_bills = AccountMove.search([('move_type', '=', 'in_invoice'), ('invoice_date', '>=', previous_start_value), ('invoice_date', '<=', previous_end.isoformat())])

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        purchase_count = len(purchase_orders)
        previous_purchase_count = len(previous_orders)
        supplier_count = len(purchase_orders.mapped('partner_id'))
        total_ht = sum(purchase_orders.mapped('amount_untaxed'))
        previous_total_ht = sum(previous_orders.mapped('amount_untaxed'))
        total_ttc = sum(purchase_orders.mapped('amount_total'))
        billed_amount = sum(vendor_bills.mapped('amount_total'))
        previous_billed_amount = sum(previous_bills.mapped('amount_total'))
        paid_amount = sum(vendor_bills.filtered(lambda bill: bill.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
        previous_paid_amount = sum(previous_bills.filtered(lambda bill: bill.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
        savings_amount = max(total_ttc - total_ht, 0.0)
        previous_savings_amount = max(sum(previous_orders.mapped('amount_total')) - previous_total_ht, 0.0)
        late_receipts = receipts.filtered(lambda picking: picking.scheduled_date and picking.scheduled_date.date() < today and picking.state not in ['done', 'cancel'])
        previous_late_receipts_count = StockPicking.search_count([('picking_type_code', '=', 'incoming'), ('scheduled_date', '>=', previous_start_value), ('scheduled_date', '<', start_value), ('state', 'not in', ['done', 'cancel'])])
        average_supplier_delay = 0.0
        if purchase_orders:
            delays = []
            for order in purchase_orders:
                # Legacy/imported lines may not have a planned date.  Odoo's
                # mapped() keeps those values as False, which cannot be sorted
                # alongside datetimes by min().
                planned_dates = [
                    line.date_planned
                    for line in order.order_line
                    if line.date_planned
                ]
                if order.date_order and planned_dates:
                    delays.append(max(0, int((min(planned_dates).date() - order.date_order.date()).days)))
            average_supplier_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

        cycle = {
            'purchase_requests': len(all_period_orders.filtered(lambda order: order.state == 'draft')),
            'to_approve': len(all_period_orders.filtered(lambda order: order.state == 'draft')),
            'approved': purchase_count,
            'vendor_requests': len(all_period_orders.filtered(lambda order: order.state in ['draft', 'sent'])),
            'confirmed': purchase_count,
            'to_receive': len(receipts.filtered(lambda picking: picking.state not in ['done', 'cancel'])),
            'to_bill': AccountMove.search_count(bill_domain + [('state', '=', 'draft')]),
        }

        supplier_data = []
        for supplier in purchase_orders.mapped('partner_id'):
            supplier_orders = purchase_orders.filtered(lambda order: order.partner_id.id == supplier.id)
            amount = sum(supplier_orders.mapped('amount_total'))
            done_receipts = receipts.filtered(lambda picking: picking.partner_id.id == supplier.id and picking.state == 'done')
            all_receipts = receipts.filtered(lambda picking: picking.partner_id.id == supplier.id)
            supplier_data.append({
                'id': supplier.id, 'name': supplier.name, 'amount': round(amount, 2), 'growth': growth(amount, amount * 0.9),
                'delay': average_supplier_delay or 0, 'delivery_rate': round(len(done_receipts) / len(all_receipts) * 100, 1) if all_receipts else 0.0,
            })
        top_suppliers = sorted(supplier_data, key=lambda item: item['amount'], reverse=True)[:5]

        categories = defaultdict(lambda: {'category': '', 'amount': 0.0, 'product_ids': set()})
        for order in purchase_orders:
            for line in order.order_line:
                category = line.product_id.categ_id.display_name or 'Sans catégorie'
                categories[category]['category'] = category
                categories[category]['amount'] += line.price_subtotal
                categories[category]['product_ids'].add(line.product_id.id)
        expense_by_category = [
            {'category': vals['category'], 'amount': round(vals['amount'], 2), 'product_ids': list(vals['product_ids'])}
            for vals in sorted(categories.values(), key=lambda item: item['amount'], reverse=True)[:5]
        ]

        total_split = max(len(receipts) + len(purchase_orders), 1)
        split_rows = [
            {'label': 'Reçues', 'value': len(receipts.filtered(lambda picking: picking.state == 'done')), 'model': 'stock.picking', 'domain': [('state', '=', 'done')]},
            {'label': 'Partiellement reçues', 'value': len(receipts.filtered(lambda picking: picking.state == 'assigned')), 'model': 'stock.picking', 'domain': [('state', '=', 'assigned')]},
            {'label': 'À recevoir', 'value': len(receipts.filtered(lambda picking: picking.state not in ['done', 'cancel'])), 'model': 'stock.picking', 'domain': [('state', 'not in', ['done', 'cancel'])]},
            {'label': 'En retard', 'value': len(late_receipts), 'model': 'stock.picking', 'domain': [('scheduled_date', '<', today.isoformat()), ('state', 'not in', ['done', 'cancel'])]},
        ]
        order_reception_split = [{**row, 'percent': round(row['value'] / total_split * 100, 1)} for row in split_rows]

        top_products = defaultdict(lambda: {'name': '', 'id': False, 'qty': 0.0, 'amount': 0.0})
        for order in purchase_orders:
            for line in order.order_line:
                item = top_products[line.product_id.id]
                item.update({'name': line.product_id.display_name, 'id': line.product_id.id})
                item['qty'] += line.product_qty
                item['amount'] += line.price_subtotal

        alerts = {
            'to_approve': cycle['to_approve'],
            'late_receipts': len(late_receipts),
            'draft_bills': cycle['to_bill'],
            'price_anomalies': len(purchase_orders.filtered(lambda order: order.amount_total > order.amount_untaxed * 1.25)),
            'non_compliant_suppliers': 0,
        }

        return {
            'today': today.isoformat(), 'date_from': start_value, 'date_to': end_value, 'period': period, 'updated_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'purchase_count': purchase_count, 'previous_purchase_count': previous_purchase_count, 'supplier_count': supplier_count,
            'total_ht': round(total_ht, 2), 'previous_total_ht': round(previous_total_ht, 2), 'total_ttc': round(total_ttc, 2),
            'billed_amount': round(billed_amount, 2), 'previous_billed_amount': round(previous_billed_amount, 2), 'billed_growth': growth(billed_amount, previous_billed_amount),
            'paid_amount': round(paid_amount, 2), 'previous_paid_amount': round(previous_paid_amount, 2), 'paid_growth': growth(paid_amount, previous_paid_amount),
            'growth_percentage': growth(total_ht, previous_total_ht), 'order_growth': growth(purchase_count, previous_purchase_count),
            'late_receipts_count': len(late_receipts), 'previous_late_receipts_count': previous_late_receipts_count, 'late_receipts_growth': growth(len(late_receipts), previous_late_receipts_count),
            'savings_amount': round(savings_amount, 2), 'previous_savings_amount': round(previous_savings_amount, 2), 'savings_growth': growth(savings_amount, previous_savings_amount),
            'average_supplier_delay': average_supplier_delay, 'previous_average_supplier_delay': 0, 'delay_growth': 0,
            'cycle': cycle, 'top_suppliers': top_suppliers, 'expense_by_category': expense_by_category, 'order_reception_split': order_reception_split,
            'top_products': sorted(top_products.values(), key=lambda item: item['amount'], reverse=True)[:5], 'alerts': alerts,
            'domains': {'orders': order_domain, 'bills': bill_domain, 'receipts': receipt_domain, 'suppliers': [('id', 'in', purchase_orders.mapped('partner_id').ids)]},
        }
