# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import fields, models

class PurchaseBillReport(models.TransientModel):
    _name = 'pt.purchase.bill'
    _description = 'Purchase Vendor Bills Report'

    def get_report_data(self, filters):
        domain = [('move_type', '=', 'in_invoice')]
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        company_id = filters.get('company_id')
        supplier_ids = filters.get('supplier_ids')
        payment_state = filters.get('payment_state')
        if date_from:
            domain.append(('invoice_date', '>=', date_from))
        if date_to:
            domain.append(('invoice_date', '<=', date_to))
        if company_id:
            domain.append(('company_id', '=', company_id))
        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))
        if payment_state and payment_state != 'all':
            domain.append(('payment_state', '=', payment_state))
        bills = self.env['account.move'].search(domain, order='invoice_date desc')
        total_untaxed = sum(bills.mapped('amount_untaxed'))
        total_tax = sum(bills.mapped('amount_tax'))
        total_amount = sum(bills.mapped('amount_total'))
        total_paid = sum(bills.mapped('amount_total')) - sum(bills.mapped('amount_residual'))
        total_residual = sum(bills.mapped('amount_residual'))
        supplier_analysis = defaultdict(lambda: {'count': 0, 'amount': 0, 'residual': 0})
        state_analysis = defaultdict(int)
        monthly_analysis = defaultdict(float)
        details = []
        for bill in bills:
            supplier_name = bill.partner_id.display_name or '-'
            supplier_analysis[supplier_name]['count'] += 1
            supplier_analysis[supplier_name]['amount'] += bill.amount_total
            supplier_analysis[supplier_name]['residual'] += bill.amount_residual
            state_analysis[bill.payment_state] += 1
            if bill.invoice_date:
                month_key = fields.Date.to_date(bill.invoice_date).strftime('%Y-%m')
                monthly_analysis[month_key] += bill.amount_total
            details.append({'number': bill.name, 'date': bill.invoice_date, 'due_date': bill.invoice_date_due, 'supplier': supplier_name, 'reference': bill.ref or '-', 'untaxed': bill.amount_untaxed, 'tax': bill.amount_tax, 'total': bill.amount_total, 'paid': bill.amount_total - bill.amount_residual, 'residual': bill.amount_residual, 'payment_state': dict(bill._fields['payment_state'].selection).get(bill.payment_state, bill.payment_state)})
        kpi = {'bill_count': len(bills), 'supplier_count': len(bills.mapped('partner_id')), 'total_untaxed': total_untaxed, 'total_tax': total_tax, 'total_amount': total_amount, 'total_paid': total_paid, 'total_residual': total_residual, 'paid_count': len(bills.filtered(lambda b: b.payment_state == 'paid')), 'partial_count': len(bills.filtered(lambda b: b.payment_state == 'partial')), 'unpaid_count': len(bills.filtered(lambda b: b.payment_state in ('not_paid', 'in_payment')))}
        return {'kpi': kpi, 'supplier_analysis': dict(supplier_analysis), 'state_analysis': dict(state_analysis), 'monthly_analysis': dict(sorted(monthly_analysis.items())), 'details': details}
