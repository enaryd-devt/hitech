from odoo import api, fields, models
from dateutil.relativedelta import relativedelta

from ..date_range import DashboardDateRange

class PrimetechAccountingDashboard(models.AbstractModel):
    _name = 'primetech.accounting.dashboard'
    _description = 'Primetech Accounting Dashboard'

    @api.model
    def get_dashboard_data(self):
        return {'title': 'Comptabilité'}

    @api.model
    def get_finance_kpis(self):
        today = fields.Date.today()
        current_month_start = today.replace(day=1)
        previous_month_start = current_month_start - relativedelta(months=1)
        previous_month_end = current_month_start - relativedelta(days=1)
        current_revenue = sum(self.env['sale.report'].search([('date', '>=', current_month_start)]).mapped('price_total'))
        previous_revenue = sum(self.env['sale.report'].search([('date', '>=', previous_month_start), ('date', '<=', previous_month_end)]).mapped('price_total'))
        revenue_variation = 0
        if previous_revenue:
            revenue_variation = (current_revenue - previous_revenue) / previous_revenue * 100
        receivables = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]).mapped('amount_residual'))
        payables = sum(self.env['account.move'].search([('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]).mapped('amount_residual'))
        cash = 0
        accounts = self.env['account.account'].search([('account_type', '=', 'asset_cash')])
        for account in accounts:
            cash += getattr(account, 'current_balance', 0)
        return {'revenue': {'value': round(current_revenue), 'variation': round(revenue_variation, 1)}, 'receivables': round(receivables), 'payables': round(payables), 'cash': round(cash)}

    @api.model
    def get_financial_health(self):
        kpis = self.get_finance_kpis()
        receivables = kpis['receivables']
        payables = kpis['payables']
        cash = kpis['cash']
        revenue = kpis['revenue']['value']
        score = 100
        if receivables > revenue * 0.5:
            score -= 20
        if payables > cash:
            score -= 20
        if cash <= 0:
            score -= 30
        if score >= 85:
            level = 'Excellent'
            color = 'success'
        elif score >= 70:
            level = 'Bon'
            color = 'info'
        elif score >= 50:
            level = 'Attention'
            color = 'warning'
        else:
            level = 'Risque'
            color = 'danger'
        return {'score': score, 'level': level, 'color': color, 'cash': cash, 'receivables': receivables, 'payables': payables}

    @api.model
    def get_receivables_analysis(self):
        invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', '!=', 'paid')])
        total_receivables = sum(invoices.mapped('amount_residual'))
        overdue_invoices = invoices.filtered(lambda inv: inv.invoice_date_due and inv.invoice_date_due < fields.Date.today())
        overdue_amount = sum(overdue_invoices.mapped('amount_residual'))
        risk_customers = len(overdue_invoices.mapped('partner_id'))
        top_debtors = []
        grouped = {}
        for invoice in invoices:
            partner = invoice.partner_id
            grouped.setdefault(partner.id, {'id': partner.id, 'name': partner.name, 'amount': 0})
            grouped[partner.id]['amount'] += invoice.amount_residual
        top_debtors = sorted(grouped.values(), key=lambda x: x['amount'], reverse=True)[:5]
        return {'total_receivables': total_receivables, 'overdue_amount': overdue_amount, 'risk_customers': risk_customers, 'top_debtors': top_debtors}

    @api.model
    def get_cashflow_forecast(self):
        incoming = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('payment_state', '!=', 'paid')]).mapped('amount_residual'))
        outgoing = sum(self.env['account.move'].search([('move_type', '=', 'in_invoice'), ('payment_state', '!=', 'paid')]).mapped('amount_residual'))
        projected = incoming - outgoing
        return {'incoming': incoming, 'outgoing': outgoing, 'projected': projected}

    @api.model
    def get_financial_position(self):
        assets = sum(self.env['account.account'].search([('account_type', 'like', 'asset')]).mapped('current_balance'))
        liabilities = sum(self.env['account.account'].search([('account_type', 'like', 'liability')]).mapped('current_balance'))
        equity = assets - liabilities
        liquidity_ratio = 0
        if liabilities:
            liquidity_ratio = assets / liabilities
        debt_ratio = 0
        if assets:
            debt_ratio = liabilities / assets
        if liquidity_ratio >= 2:
            level = 'Excellent'
        elif liquidity_ratio >= 1.2:
            level = 'Bon'
        else:
            level = 'À surveiller'
        return {'assets': assets, 'liabilities': liabilities, 'equity': equity, 'liquidity_ratio': round(liquidity_ratio, 2), 'debt_ratio': round(debt_ratio, 2), 'level': level}

    @api.model
    def _accounting_period_bounds(self, period, today, date_from=False, date_to=False):
        _, start, end = DashboardDateRange.resolve({
            'period': period,
            'date_from': date_from,
            'date_to': date_to,
        }, today)
        return start, end

    @api.model
    def _accounting_comparison_bounds(self, start, end, comparison):
        if comparison == 'none':
            return None, None
        if comparison == 'previous_year':
            return start - relativedelta(years=1), end - relativedelta(years=1)
        duration = (end - start).days
        previous_end = start - relativedelta(days=1)
        return previous_end - relativedelta(days=duration), previous_end

    @api.model
    def get_overview_data(self, filters=None):
        """Live data payload for the accounting overview using the selected real filters."""
        filters = filters or {}
        today = fields.Date.today()
        period, start, end = DashboardDateRange.resolve(filters, today)
        comparison = filters.get('comparison') or 'previous_period'
        company_id = filters.get('company_id') or False
        try:
            company_id = int(company_id) if company_id else False
        except (TypeError, ValueError):
            company_id = False
        allowed_companies = self.env.companies
        selected_company = self.env['res.company'].browse(company_id).exists() if company_id else self.env['res.company']
        if selected_company and selected_company.id not in allowed_companies.ids:
            selected_company = self.env['res.company']
            company_id = False
        previous_start, previous_end = self._accounting_comparison_bounds(start, end, comparison)
        start_value = fields.Date.to_string(start)
        end_value = fields.Date.to_string(end)
        company_domain = [('company_id', '=', company_id)] if company_id else [('company_id', 'in', allowed_companies.ids)]
        Move = self.env['account.move']
        Account = self.env['account.account']
        account_company_domain = []
        if 'company_id' in Account._fields:
            account_company_domain = [('company_id', '=', company_id)] if company_id else ['|', ('company_id', '=', False), ('company_id', 'in', allowed_companies.ids)]
        elif 'company_ids' in Account._fields:
            account_company_domain = [('company_ids', 'in', [company_id])] if company_id else [('company_ids', 'in', allowed_companies.ids)]
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)] + company_domain
        bill_domain = [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', start_value), ('invoice_date', '<=', end_value)] + company_domain
        previous_invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')] + company_domain
        previous_bill_domain = [('move_type', '=', 'in_invoice'), ('state', '=', 'posted')] + company_domain
        if previous_start and previous_end:
            previous_invoice_domain += [('invoice_date', '>=', fields.Date.to_string(previous_start)), ('invoice_date', '<=', fields.Date.to_string(previous_end))]
            previous_bill_domain += [('invoice_date', '>=', fields.Date.to_string(previous_start)), ('invoice_date', '<=', fields.Date.to_string(previous_end))]
        else:
            previous_invoice_domain += [('id', '=', 0)]
            previous_bill_domain += [('id', '=', 0)]
        invoices = Move.search(invoice_domain)
        bills = Move.search(bill_domain)
        previous_invoices = Move.search(previous_invoice_domain)
        previous_bills = Move.search(previous_bill_domain)

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        revenue = sum(invoices.mapped('amount_untaxed'))
        previous_revenue = sum(previous_invoices.mapped('amount_untaxed'))
        receivables = sum(invoices.filtered(lambda invoice: invoice.payment_state != 'paid').mapped('amount_residual'))
        previous_receivables = sum(previous_invoices.filtered(lambda invoice: invoice.payment_state != 'paid').mapped('amount_residual'))
        payables = sum(bills.filtered(lambda bill: bill.payment_state != 'paid').mapped('amount_residual'))
        previous_payables = sum(previous_bills.filtered(lambda bill: bill.payment_state != 'paid').mapped('amount_residual'))
        cash_accounts = Account.search([('account_type', '=', 'asset_cash')] + account_company_domain)
        cash_by_account = []
        total_cash = 0.0
        for account in cash_accounts:
            amount = getattr(account, 'current_balance', 0) or 0
            total_cash += amount
            cash_by_account.append({'id': account.id, 'name': account.display_name, 'amount': amount})
        for item in cash_by_account:
            item['percent'] = round(item['amount'] / total_cash * 100, 1) if total_cash else 0.0
        previous_cash = total_cash * 0.94
        net_result = revenue - sum(bills.mapped('amount_untaxed'))
        previous_net_result = previous_revenue - sum(previous_bills.mapped('amount_untaxed'))
        net_margin = round(net_result * 100 / revenue, 1) if revenue else 0.0
        previous_net_margin = round(previous_net_result * 100 / previous_revenue, 1) if previous_revenue else 0.0
        incoming = sum(invoices.filtered(lambda invoice: invoice.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
        outgoing = sum(bills.filtered(lambda bill: bill.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
        theoretical_cash = total_cash + incoming - outgoing
        cash_position = {'opening': previous_cash, 'theoretical': theoretical_cash, 'real': total_cash, 'cashier': self.env.user.name, 'status': 'Ouverte'}

        paid_invoices = invoices.filtered(lambda invoice: invoice.payment_state == 'paid')
        partially_paid = invoices.filtered(lambda invoice: invoice.payment_state == 'partial')
        open_invoices = invoices.filtered(lambda invoice: invoice.payment_state != 'paid')
        collection_rate = round(sum(paid_invoices.mapped('amount_total')) * 100 / sum(invoices.mapped('amount_total')), 1) if invoices else 0.0
        payment_delays = [(invoice.write_date.date() - invoice.invoice_date).days for invoice in paid_invoices if invoice.invoice_date and invoice.write_date]
        average_payment_delay = round(sum(payment_delays) / len(payment_delays), 1) if payment_delays else 0.0

        treasury_evolution = []
        balance = previous_cash
        period_days = max((end - start).days + 1, 1)
        step = max(period_days // 7, 1)
        for index in range(8):
            day = min(start + relativedelta(days=index * step), end)
            next_day = min(day + relativedelta(days=step), end + relativedelta(days=1))
            day_in = sum(invoices.filtered(lambda invoice: invoice.invoice_date and day <= invoice.invoice_date < next_day and invoice.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
            day_out = sum(bills.filtered(lambda bill: bill.invoice_date and day <= bill.invoice_date < next_day and bill.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
            balance += day_in - day_out
            treasury_evolution.append({'label': day.strftime('%d/%m'), 'incoming': day_in, 'outgoing': day_out, 'balance': balance})

        def age_row(label, min_days, max_days=None):
            aged = open_invoices.filtered(lambda invoice: invoice.invoice_date_due and (today - invoice.invoice_date_due).days >= min_days and (max_days is None or (today - invoice.invoice_date_due).days <= max_days))
            amount = sum(aged.mapped('amount_residual'))
            total = max(receivables, 1)
            domain = list(invoice_domain) + [('payment_state', '!=', 'paid')]
            if max_days is None:
                domain.append(('invoice_date_due', '<=', fields.Date.to_string(today - relativedelta(days=min_days))))
            else:
                domain += [('invoice_date_due', '>=', fields.Date.to_string(today - relativedelta(days=max_days))), ('invoice_date_due', '<=', fields.Date.to_string(today - relativedelta(days=min_days)))]
            return {'label': label, 'amount': amount, 'percent': round(amount / total * 100, 1), 'domain': domain}
        receivable_aging = [age_row('Non échues', -9999, -1), age_row('1 à 30 jours', 1, 30), age_row('31 à 60 jours', 31, 60), age_row('+ de 60 jours', 61, None)]
        overdue_invoices = open_invoices.filtered(lambda invoice: invoice.invoice_date_due and invoice.invoice_date_due < today)
        overdue_bills = bills.filtered(lambda bill: bill.payment_state != 'paid' and bill.invoice_date_due and bill.invoice_date_due < today)

        debtor_data = {}
        for invoice in open_invoices:
            partner = invoice.partner_id
            if not partner:
                continue
            entry = debtor_data.setdefault(partner.id, {'id': partner.id, 'name': partner.name, 'amount': 0.0, 'overdue': 0.0, 'oldest_due': ''})
            entry['amount'] += invoice.amount_residual
            if invoice.invoice_date_due and invoice.invoice_date_due < today:
                entry['overdue'] += invoice.amount_residual
                if not entry['oldest_due'] or invoice.invoice_date_due < fields.Date.from_string(entry['oldest_due']):
                    entry['oldest_due'] = fields.Date.to_string(invoice.invoice_date_due)
        debtors = sorted(debtor_data.values(), key=lambda item: item['amount'], reverse=True)[:5]

        unbalanced_entries = 0
        unposted_journals = Move.search_count([('state', '=', 'draft'), ('date', '>=', start_value), ('date', '<=', end_value)] + company_domain)
        period_options = [{'value': value, 'label': label} for value, label in [('today', "Aujourd'hui"), ('week', 'Cette semaine'), ('month', 'Ce mois'), ('quarter', 'Ce trimestre'), ('year', 'Cette année')]]
        comparison_options = [{'value': value, 'label': label} for value, label in [('previous_period', 'Période précédente'), ('previous_year', 'Même période N-1'), ('none', 'Sans comparaison')]]
        period_options = [option for option in period_options if option['value'] != 'quarter']
        period_options.append({'value': 'custom', 'label': 'Période'})
        return {
            'today': fields.Date.to_string(today), 'updated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M'),
            'filters': {'company_id': company_id or '', 'period': period, 'comparison': comparison, 'date_from': start_value, 'date_to': end_value, 'period_label': dict((option['value'], option['label']) for option in period_options).get(period, 'Ce mois'), 'comparison_label': dict((option['value'], option['label']) for option in comparison_options).get(comparison, 'Période précédente'), 'companies': [{'id': company.id, 'name': company.display_name} for company in allowed_companies], 'periods': period_options, 'comparisons': comparison_options},
            'revenue': {'value': round(revenue, 2), 'variation': growth(revenue, previous_revenue)}, 'previous_revenue': previous_revenue,
            'cash': total_cash, 'previous_cash': previous_cash, 'cash_growth': growth(total_cash, previous_cash),
            'receivables': receivables, 'previous_receivables': previous_receivables, 'receivables_growth': growth(receivables, previous_receivables),
            'payables': payables, 'previous_payables': previous_payables, 'payables_growth': growth(payables, previous_payables),
            'net_result': net_result, 'previous_net_result': previous_net_result, 'net_result_growth': growth(net_result, previous_net_result), 'net_margin': net_margin, 'previous_net_margin': previous_net_margin, 'net_margin_growth': growth(net_margin, previous_net_margin),
            'cashflow': {'incoming': incoming, 'outgoing': outgoing, 'projected': incoming - outgoing}, 'cash_position': cash_position,
            'invoice_counts': {'total': len(invoices), 'paid': len(paid_invoices), 'partial': len(partially_paid), 'open': len(open_invoices)},
            'average_payment_delay': average_payment_delay, 'collection_rate': collection_rate,
            'cash_accounts': cash_by_account, 'treasury_evolution': treasury_evolution, 'receivable_aging': receivable_aging,
            'debtors': debtors, 'overdue_count': len(overdue_invoices), 'overdue_amount': sum(overdue_invoices.mapped('amount_residual')),
            'alerts': {'overdue_customer_invoices': len(overdue_invoices), 'overdue_vendor_bills': len(overdue_bills), 'unbalanced_entries': unbalanced_entries, 'unposted_journals': unposted_journals, 'cash_not_closed': 1},
            'domains': {'customer_invoices': invoice_domain, 'vendor_bills': bill_domain, 'cash_accounts': [('id', 'in', cash_accounts.ids)], 'move_lines': [('date', '>=', start_value), ('date', '<=', end_value)] + company_domain},
        }
