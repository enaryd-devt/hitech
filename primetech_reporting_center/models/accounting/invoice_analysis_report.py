from collections import defaultdict
from datetime import date
from odoo import api
from odoo import fields
from odoo import models

class InvoiceAnalysisReport(models.AbstractModel):
    _name = 'primetech.invoice.analysis.report'
    _description = 'Analyse de Facturation'

    @api.model
    def get_report_data(self, date_from, date_to, company_id=False, partner_id=False, user_id=False, move_type=False, payment_state=False):
        domain = [('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        if user_id:
            domain.append(('invoice_user_id', '=', user_id))
        if move_type:
            domain.append(('move_type', '=', move_type))
        if payment_state:
            domain.append(('payment_state', '=', payment_state))
        invoices = self.env['account.move'].search(domain, order='invoice_date desc')
        customer_ids = set()
        total_ht = 0.0
        total_tax = 0.0
        total_ttc = 0.0
        total_residual = 0.0
        total_paid = 0.0
        total_refund = 0.0
        payment_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        customer_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        product_summary = defaultdict(lambda: {'qty': 0.0, 'amount': 0.0})
        salesperson_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0, 'paid': 0.0})
        tax_summary = defaultdict(lambda: {'base': 0.0, 'tax': 0.0})
        monthly_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0, 'tax': 0.0})
        overdue_invoices = []
        large_unpaid = []
        invoice_lines = []
        product_lines = []
        largest_invoice = None
        today = fields.Date.today()
        for invoice in invoices:
            customer_ids.add(invoice.partner_id.id)
            total_ht += invoice.amount_untaxed
            total_tax += invoice.amount_tax
            total_ttc += invoice.amount_total
            total_residual += invoice.amount_residual
            total_paid += invoice.amount_total - invoice.amount_residual
            if invoice.move_type == 'out_refund':
                total_refund += invoice.amount_total
            payment_summary[invoice.payment_state]['count'] += 1
            payment_summary[invoice.payment_state]['amount'] += invoice.amount_total
            customer_summary[invoice.partner_id.name]['count'] += 1
            customer_summary[invoice.partner_id.name]['amount'] += invoice.amount_total
            salesperson = invoice.invoice_user_id.name if invoice.invoice_user_id else 'Non affecté'
            salesperson_summary[salesperson]['count'] += 1
            salesperson_summary[salesperson]['amount'] += invoice.amount_total
            salesperson_summary[salesperson]['paid'] += invoice.amount_total - invoice.amount_residual
            period = invoice.invoice_date.strftime('%Y-%m')
            monthly_summary[period]['count'] += 1
            monthly_summary[period]['amount'] += invoice.amount_total
            monthly_summary[period]['tax'] += invoice.amount_tax
            for line in invoice.invoice_line_ids:
                if not line.product_id:
                    continue
                product_summary[line.product_id.display_name]['qty'] += line.quantity
                product_summary[line.product_id.display_name]['amount'] += line.price_total
                product_lines.append({'invoice': invoice.name, 'date': invoice.invoice_date, 'customer': invoice.partner_id.name, 'product': line.product_id.display_name, 'qty': line.quantity, 'unit_price': line.price_unit, 'discount': line.discount, 'subtotal': line.price_subtotal, 'total': line.price_total})
                for tax in line.tax_ids:
                    tax_summary[tax.name]['base'] += line.price_subtotal
                    tax_summary[tax.name]['tax'] += line.price_total - line.price_subtotal
            if largest_invoice is None or invoice.amount_total > largest_invoice['amount']:
                largest_invoice = {'name': invoice.name, 'customer': invoice.partner_id.name, 'amount': invoice.amount_total}
            if invoice.invoice_date_due and invoice.invoice_date_due < today and (invoice.amount_residual > 0):
                overdue_invoices.append({'invoice': invoice.name, 'customer': invoice.partner_id.name, 'due_date': invoice.invoice_date_due, 'residual': invoice.amount_residual})
            if invoice.amount_residual > 1000000:
                large_unpaid.append({'invoice': invoice.name, 'customer': invoice.partner_id.name, 'residual': invoice.amount_residual})
            invoice_lines.append({'invoice': invoice.name, 'date': invoice.invoice_date, 'customer': invoice.partner_id.name, 'salesperson': salesperson, 'payment_state': invoice.payment_state, 'ht': invoice.amount_untaxed, 'tax': invoice.amount_tax, 'ttc': invoice.amount_total, 'residual': invoice.amount_residual})
        payment_rate = total_paid * 100 / total_ttc if total_ttc else 0
        summary = {'invoice_count': len(invoices), 'customer_count': len(customer_ids), 'total_ht': total_ht, 'total_tax': total_tax, 'total_ttc': total_ttc, 'paid_amount': total_paid, 'residual_amount': total_residual, 'payment_rate': payment_rate, 'average_invoice': total_ttc / len(invoices) if invoices else 0, 'refund_amount': total_refund, 'largest_invoice': largest_invoice}
        return {'summary': summary, 'payment_summary': dict(payment_summary), 'customer_ranking': sorted([{'customer': k, **v} for k, v in customer_summary.items()], key=lambda x: x['amount'], reverse=True)[:20], 'product_ranking': sorted([{'product': k, **v} for k, v in product_summary.items()], key=lambda x: x['amount'], reverse=True)[:20], 'salesperson_ranking': sorted([{'salesperson': k, **v} for k, v in salesperson_summary.items()], key=lambda x: x['amount'], reverse=True), 'tax_summary': dict(tax_summary), 'monthly_summary': dict(monthly_summary), 'alerts': {'overdue': overdue_invoices, 'large_unpaid': large_unpaid}, 'invoice_lines': invoice_lines, 'product_lines': product_lines}
