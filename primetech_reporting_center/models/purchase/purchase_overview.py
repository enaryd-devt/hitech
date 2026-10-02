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
        """Build the purchase dashboard from vendor bills, not purchase orders.

        This database records procurement directly on supplier invoices.  Using
        ``account.move`` here keeps every amount, supplier and product shown on
        the dashboard aligned with the accounting documents actually entered.
        """
        filters = filters or {}
        today = date.today()
        period, start, end = self._period_bounds(filters, today)
        start_value, end_value = start.isoformat(), end.isoformat()
        end_exclusive = (end + timedelta(days=1)).isoformat()
        previous_start, previous_end = DashboardDateRange.previous_bounds(start, end)
        AccountMove = self.env['account.move']
        StockPicking = self.env['stock.picking']

        bill_date_domain = [('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)]
        bill_domain = [('move_type', '=', 'in_invoice'), ('state', '=', 'posted')] + bill_date_domain
        draft_bill_domain = [('move_type', '=', 'in_invoice'), ('state', '=', 'draft')] + bill_date_domain
        receipt_domain = [('picking_type_code', '=', 'incoming'), ('scheduled_date', '>=', start_value), ('scheduled_date', '<', end_exclusive)]
        previous_bill_domain = [
            ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
            ('invoice_date', '>=', previous_start.isoformat()), ('invoice_date', '<=', previous_end.isoformat()),
        ]
        vendor_bills = AccountMove.search(bill_domain)
        draft_bills = AccountMove.search(draft_bill_domain)
        previous_bills = AccountMove.search(previous_bill_domain)
        receipts = StockPicking.search(receipt_domain)

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        total_ht = sum(vendor_bills.mapped('amount_untaxed'))
        total_ttc = sum(vendor_bills.mapped('amount_total'))
        previous_total_ht = sum(previous_bills.mapped('amount_untaxed'))
        previous_total_ttc = sum(previous_bills.mapped('amount_total'))
        paid_amount = sum(bill.amount_total - bill.amount_residual for bill in vendor_bills)
        previous_paid_amount = sum(bill.amount_total - bill.amount_residual for bill in previous_bills)
        outstanding_amount = sum(vendor_bills.mapped('amount_residual'))
        previous_outstanding = sum(previous_bills.mapped('amount_residual'))
        late_receipts = receipts.filtered(lambda picking: picking.scheduled_date and picking.scheduled_date.date() < today and picking.state not in ['done', 'cancel'])
        previous_late_receipts_count = StockPicking.search_count([
            ('picking_type_code', '=', 'incoming'), ('scheduled_date', '>=', previous_start.isoformat()),
            ('scheduled_date', '<', start_value), ('state', 'not in', ['done', 'cancel']),
        ])

        cycle = {
            'purchase_requests': len(draft_bills),
            'to_approve': len(draft_bills),
            'approved': len(vendor_bills),
            'vendor_requests': len(draft_bills),
            'confirmed': len(vendor_bills),
            'to_receive': len(receipts.filtered(lambda picking: picking.state not in ['done', 'cancel'])),
            'to_bill': len(draft_bills),
        }

        supplier_data = []
        for supplier in vendor_bills.mapped('partner_id'):
            supplier_bills = vendor_bills.filtered(lambda bill: bill.partner_id.id == supplier.id)
            amount = sum(supplier_bills.mapped('amount_total'))
            supplier_receipts = receipts.filtered(lambda picking: picking.partner_id.id == supplier.id)
            done_receipts = supplier_receipts.filtered(lambda picking: picking.state == 'done')
            supplier_data.append({
                'id': supplier.id, 'name': supplier.display_name, 'amount': round(amount, 2),
                'growth': growth(amount, 0.0), 'delay': 0,
                'delivery_rate': round(len(done_receipts) / len(supplier_receipts) * 100, 1) if supplier_receipts else 0.0,
            })

        categories = defaultdict(lambda: {'category': '', 'amount': 0.0, 'product_ids': set()})
        top_products = defaultdict(lambda: {'name': '', 'id': False, 'qty': 0.0, 'amount': 0.0})
        for line in vendor_bills.mapped('invoice_line_ids').filtered(lambda row: row.product_id and not row.display_type):
            category = line.product_id.categ_id.display_name or 'Sans catégorie'
            categories[category]['category'] = category
            categories[category]['amount'] += line.price_subtotal
            categories[category]['product_ids'].add(line.product_id.id)
            item = top_products[line.product_id.id]
            item.update({'name': line.product_id.display_name, 'id': line.product_id.id})
            item['qty'] += line.quantity
            item['amount'] += line.price_subtotal
        expense_by_category = [
            {'category': value['category'], 'amount': round(value['amount'], 2), 'product_ids': list(value['product_ids'])}
            for value in sorted(categories.values(), key=lambda item: item['amount'], reverse=True)[:5]
        ]

        receipt_rows = [
            {'label': 'Factures validées', 'value': len(vendor_bills), 'model': 'account.move', 'domain': [('state', '=', 'posted')]},
            {'label': 'Factures brouillon', 'value': len(draft_bills), 'model': 'account.move', 'domain': [('state', '=', 'draft')]},
            {'label': 'Réceptions terminées', 'value': len(receipts.filtered(lambda picking: picking.state == 'done')), 'model': 'stock.picking', 'domain': [('state', '=', 'done')]},
            {'label': 'Réceptions à traiter', 'value': len(receipts.filtered(lambda picking: picking.state not in ['done', 'cancel'])), 'model': 'stock.picking', 'domain': [('state', 'not in', ['done', 'cancel'])]},
        ]
        split_total = max(sum(row['value'] for row in receipt_rows), 1)
        order_reception_split = [{**row, 'percent': round(row['value'] / split_total * 100, 1)} for row in receipt_rows]

        alerts = {
            'to_approve': len(draft_bills), 'late_receipts': len(late_receipts), 'draft_bills': len(draft_bills),
            'price_anomalies': len(vendor_bills.filtered(lambda bill: bill.amount_residual > 0 and bill.invoice_date_due and bill.invoice_date_due < today)),
            'non_compliant_suppliers': 0,
        }
        supplier_ids = vendor_bills.mapped('partner_id').ids
        return {
            'today': today.isoformat(), 'date_from': start_value, 'date_to': end_value, 'period': period,
            'updated_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'purchase_count': len(vendor_bills), 'previous_purchase_count': len(previous_bills), 'supplier_count': len(supplier_ids),
            'total_ht': round(total_ht, 2), 'previous_total_ht': round(previous_total_ht, 2), 'total_ttc': round(total_ttc, 2),
            'billed_amount': round(total_ttc, 2), 'previous_billed_amount': round(previous_total_ttc, 2), 'billed_growth': growth(total_ttc, previous_total_ttc),
            'paid_amount': round(paid_amount, 2), 'previous_paid_amount': round(previous_paid_amount, 2), 'paid_growth': growth(paid_amount, previous_paid_amount),
            'growth_percentage': growth(total_ht, previous_total_ht), 'order_growth': growth(len(vendor_bills), len(previous_bills)),
            'late_receipts_count': len(late_receipts), 'previous_late_receipts_count': previous_late_receipts_count,
            'late_receipts_growth': growth(len(late_receipts), previous_late_receipts_count),
            'savings_amount': round(outstanding_amount, 2), 'previous_savings_amount': round(previous_outstanding, 2), 'savings_growth': growth(outstanding_amount, previous_outstanding),
            'average_supplier_delay': 0.0, 'previous_average_supplier_delay': 0.0, 'delay_growth': 0.0,
            'cycle': cycle, 'top_suppliers': sorted(supplier_data, key=lambda item: item['amount'], reverse=True)[:5],
            'expense_by_category': expense_by_category, 'order_reception_split': order_reception_split,
            'top_products': sorted(top_products.values(), key=lambda item: item['amount'], reverse=True)[:5], 'alerts': alerts,
            'domains': {'orders': bill_domain, 'bills': bill_domain, 'draft_bills': draft_bill_domain, 'receipts': receipt_domain, 'suppliers': [('id', 'in', supplier_ids)]},
        }
