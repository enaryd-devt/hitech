import json

from odoo import _, api, models, fields
from datetime import date, timedelta
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import unicodedata

class PrimetechDashboard(models.AbstractModel):
    _name = 'primetech.dashboard'
    _description = 'PrimeTech Dashboard Service'


    def _sum_pos_orders(self, domain):
        if 'pos.order' not in self.env.registry:
            return 0.0
        return sum(self.env['pos.order'].search(domain).mapped('amount_total'))

    def _get_sales_purchase_cost(self, date_from=None, date_to=None):
        """Return the purchase cost of the products included in turnover."""
        invoice_domain = [
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('product_id', '!=', False),
        ]
        if date_from:
            invoice_domain.append(('move_id.invoice_date', '>=', date_from))
        if date_to:
            invoice_domain.append(('move_id.invoice_date', '<=', date_to))
        InvoiceLine = self.env['account.move.line']
        has_purchase_price = 'purchase_price' in InvoiceLine._fields
        purchase_cost = 0.0
        for line in InvoiceLine.search(invoice_domain):
            unit_cost = line.purchase_price if has_purchase_price else line.product_id.standard_price
            purchase_cost += (line.quantity or 0.0) * (unit_cost or 0.0)

        if 'pos.order.line' in self.env.registry:
            pos_domain = [('product_id', '!=', False)]
            if date_from:
                pos_domain.append(('order_id.date_order', '>=', date_from))
            if date_to:
                pos_domain.append(('order_id.date_order', '<', fields.Datetime.to_datetime(date_to) + timedelta(days=1)))
            for line in self.env['pos.order.line'].search(pos_domain):
                purchase_cost += (line.qty or 0.0) * (line.product_id.standard_price or 0.0)
        return purchase_cost

    def _get_period_bounds(self, filters=None):
        filters = filters or {}
        today = date.today()
        period = filters.get('period', 'month')
        if period == 'today':
            return today, today
        if period == 'week':
            return today - timedelta(days=today.weekday()), today
        if period == 'year':
            return today.replace(month=1, day=1), today
        if period == 'quarter':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            return today.replace(month=quarter_month, day=1), today
        if period == 'custom':
            start = fields.Date.to_date(filters.get('date_from')) if filters.get('date_from') else today.replace(day=1)
            end = fields.Date.to_date(filters.get('date_to')) if filters.get('date_to') else today
            return (start, end) if start <= end else (end, start)
        return today.replace(day=1), today


    def _categorize_journal(self, journal):
        label = f"{journal.name or ''} {journal.code or ''}".lower()
        if any(token in label for token in ('momo', 'mobile money', 'mtn')):
            return 'MOMO'
        if any(token in label for token in ('om', 'orange money', 'orange')):
            return 'OM'
        if any(token in label for token in ('cash', 'caisse', 'espèce', 'espece', 'espèces', 'especes')):
            return 'Espèce'
        if journal.type == 'bank' or any(token in label for token in ('bank', 'banque')):
            return 'Banque'
        if journal.type == 'cash':
            return 'Espèce'
        return 'Autres'

    def _group_amounts_by_journal_category(self, records, amount_field='amount'):
        grouped = defaultdict(float)
        for record in records:
            journal = record.journal_id
            grouped[self._categorize_journal(journal)] += getattr(record, amount_field, 0.0) or 0.0
        return [{'category': key, 'amount': value} for key, value in sorted(grouped.items())]

    def _period_filter_value(self, filters, key, default=None):
        filters = filters or {}
        return filters.get(key) or filters.get('kpi_filters', {}).get(key) or default or filters.get('period', 'month')

    def _scoped_period_filters(self, filters, key, default=None):
        """Build period filters for an individual dashboard card."""
        scoped = dict(filters or {})
        scoped['period'] = self._period_filter_value(filters, key, default)
        custom_range = (filters or {}).get('kpi_custom_ranges', {}).get(key, {})
        if scoped['period'] == 'custom':
            scoped['date_from'] = custom_range.get('date_from')
            scoped['date_to'] = custom_range.get('date_to')
        else:
            scoped.pop('date_from', None)
            scoped.pop('date_to', None)
        return scoped

    def _period_domain(self, filters, field_name, key=None):
        period_filters = dict(filters or {})
        if key:
            period_filters['period'] = self._period_filter_value(filters, key, period_filters.get('period', 'month'))
        return self._get_date_domain(period_filters, field_name)

    def _dashboard_open_model(self, name, model, domain=None, context=None, views=None):
        """Create a standard drill-down action for a lightweight KPI payload."""
        view_mode = views or 'list,form'
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': view_mode,
            'views': [[False, mode] for mode in view_mode.split(',')],
            'domain': domain or [],
            'context': context or {},
        }

    def _get_pos_session_state(self, filters=None):
        filters = filters or {}
        if 'pos.session' not in self.env.registry:
            return {'opened': 0, 'closed': 0, 'opening_balance': 0.0, 'current_balance': 0.0, 'closing_balance': 0.0, 'sessions': []}
        # Keep every session in the selected period: the client constrains the
        # viewport to eight compact rows and lets the user scroll through the
        # complete result set.
        sessions = self.env['pos.session'].search(self._get_date_domain(filters, 'start_at'), order='start_at desc, id desc')
        opened = sessions.filtered(lambda session: session.state not in ('closed', 'closing_control'))
        closed = sessions.filtered(lambda session: session.state in ('closed', 'closing_control'))
        session_lines = []
        for session in sessions:
            orders_total = sum(session.order_ids.mapped('amount_total')) if hasattr(session, 'order_ids') else 0.0
            opening_balance = getattr(session, 'cash_register_balance_start', 0.0) or 0.0
            real_balance = getattr(session, 'cash_register_balance_end_real', 0.0) or 0.0
            theoretical_balance = getattr(session, 'cash_register_balance_end', 0.0) or opening_balance + orders_total
            journal = getattr(getattr(session, 'config_id', False), 'journal_id', False)
            is_closed = session.state in ('closed', 'closing_control')
            session_lines.append({
                'id': session.id,
                'name': session.config_id.name or session.name,
                'state': 'Clôturé' if is_closed else 'En cours',
                'raw_state': session.state,
                'status_class': 'closed' if is_closed else 'open',
                'user': session.user_id.name or '-',
                'cashier': session.user_id.name or '-',
                'journal': journal.display_name if journal else '-',
                'opening_date': session.start_at.strftime('%d/%m/%Y %H:%M') if session.start_at else '-',
                'closing_date': session.stop_at.strftime('%d/%m/%Y %H:%M') if session.stop_at else '-',
                'opening_balance': opening_balance,
                'current_balance': theoretical_balance,
                'closing_balance': real_balance,
                'balance': real_balance if is_closed else theoretical_balance,
                'orders_total': orders_total,
            })
        return {
            'opened': len(opened),
            'closed': len(closed),
            'opening_balance': sum(getattr(s, 'cash_register_balance_start', 0.0) or 0.0 for s in sessions),
            'current_balance': sum((getattr(s, 'cash_register_balance_end', 0.0) or 0.0) for s in sessions),
            'closing_balance': sum((getattr(s, 'cash_register_balance_end_real', 0.0) or 0.0) for s in closed),
            'sessions': session_lines,
        }

    @api.model
    def get_executive_overview(self, filters=None):
        filters = filters or {}
        start, end = self._get_period_bounds(filters)
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', start), ('invoice_date', '<=', end)]
        invoice_revenue = sum(self.env['account.move'].search(invoice_domain).mapped('amount_total'))
        pos_domain = [
            ('date_order', '>=', start),
            ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
        ]
        pos_revenue = self._sum_pos_orders(pos_domain)
        revenue_total = invoice_revenue + pos_revenue
        purchase_cost = self._get_sales_purchase_cost(start, end)
        purchase_total = sum(self.env['purchase.order'].search([
            ('state', 'in', ['purchase', 'done']),
            ('date_approve', '>=', start),
            ('date_approve', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
        ]).mapped('amount_total'))
        stock_value = sum(product.qty_available * product.standard_price for product in self.env['product.product'].search([]))
        return {
            'period_label': {'today': "Aujourd'hui", 'week': 'Cette semaine', 'month': 'Ce mois', 'quarter': 'Ce trimestre', 'year': 'Cette année', 'custom': 'Période sélectionnée'}.get(filters.get('period', 'month'), 'Ce mois'),
            'revenue_total': revenue_total,
            'invoice_revenue': invoice_revenue,
            'pos_revenue': pos_revenue,
            'gross_margin': revenue_total - purchase_cost,
            'purchase_cost': purchase_cost,
            'purchase_total': purchase_total,
            'stock_value': stock_value,
            'bank_balance': sum(self.env['account.account'].search([('account_type', '=', 'asset_cash')]).mapped('current_balance')),
            'cash_registers': self._get_pos_session_state(self._scoped_period_filters(filters, 'cash_period', filters.get('period', 'today'))),
            'stock_alerts': {
                'out_of_stock': self.env['product.product'].search_count([('qty_available', '<=', 0), ('type', '=', 'product')]),
                'pending_transfers': self.env['stock.picking'].search_count([('state', 'not in', ('done', 'cancel'))]),
            },
            'hr': {
                'employees': self.env['hr.employee'].search_count([]) if 'hr.employee' in self.env.registry else 0,
                'on_leave': self.env['hr.leave'].search_count([('state', '=', 'validate')]) if 'hr.leave' in self.env.registry else 0,
            },
        }


    @api.model
    def get_executive_detail_sections(self, filters=None):
        filters = filters or {}
        overview = self.get_executive_overview(filters)
        sales_orders = self.env['sale.order'].search_count([('state', 'in', ('sale', 'done'))]) if 'sale.order' in self.env.registry else 0
        pending_deliveries = self.env['stock.picking'].search_count([('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))])
        pending_receipts = self.env['stock.picking'].search_count([('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel'))])
        vendor_bills = self.env['account.move'].search_count([('move_type', '=', 'in_invoice'), ('state', '=', 'draft')])
        return {
            'sections': [
                {
                    'key': 'director',
                    'title': 'Direction Générale',
                    'subtitle': 'Vue globale, rentabilité, alertes',
                    'icon': 'fa fa-dashboard',
                    'action': 'primetech_reporting_center.action_primetech_reporting_dashboard',
                    'tone': 'black',
                    'metrics': [
                        {'label': 'CA temps réel', 'value': overview['revenue_total'], 'format': 'currency'},
                        {'label': 'Marge brute', 'value': overview['gross_margin'], 'format': 'currency'},
                        {'label': 'Banque', 'value': overview['bank_balance'], 'format': 'currency'},
                        {'label': 'Alertes stock', 'value': overview['stock_alerts']['out_of_stock'], 'format': 'number'},
                    ],
                },
                {
                    'key': 'finance',
                    'title': 'Finances & Comptabilité',
                    'subtitle': 'Trésorerie, dépenses, paiements, journaux',
                    'icon': 'fa fa-university',
                    'action': actions['finance'],
                    'tone': 'white',
                    'metrics': [
                        {'label': 'Situation bancaire', 'value': overview['bank_balance'], 'format': 'currency'},
                        {'label': 'Achats validés', 'value': overview['purchase_total'], 'format': 'currency'},
                        {'label': 'Factures fournisseurs', 'value': vendor_bills, 'format': 'number'},
                        {'label': 'Factures fournisseurs', 'value': vendor_bills, 'format': 'number'},
                    ],
                },
                {
                    'key': 'sales_cash',
                    'title': 'Ventes, PDV & Caisses',
                    'subtitle': 'Facturation, encaissement, ouverture/clôture',
                    'icon': 'fa fa-credit-card',
                    'action': actions['sales'],
                    'tone': 'black',
                    'metrics': [
                        {'label': 'Facturation', 'value': overview['invoice_revenue'], 'format': 'currency'},
                        {'label': 'Ventes PDV', 'value': overview['pos_revenue'], 'format': 'currency'},
                        {'label': 'Caisses ouvertes', 'value': overview['cash_registers']['opened'], 'format': 'number'},
                        {'label': 'Solde courant', 'value': overview['cash_registers']['current_balance'], 'format': 'currency'},
                    ],
                },
                {
                    'key': 'stock_supply',
                    'title': 'Stocks & Supply Chain',
                    'subtitle': 'Magasins, transferts, livraisons, ruptures',
                    'icon': 'fa fa-truck',
                    'action': out_action,
                    'tone': 'white',
                    'metrics': [
                        {'label': 'Valeur stock', 'value': overview['stock_value'], 'format': 'currency'},
                        {'label': 'Ruptures', 'value': overview['stock_alerts']['out_of_stock'], 'format': 'number'},
                        {'label': 'Transferts', 'value': overview['stock_alerts']['pending_transfers'], 'format': 'number'},
                        {'label': 'Livraisons', 'value': pending_deliveries, 'format': 'number'},
                    ],
                },
                {
                    'key': 'operations',
                    'title': 'Exploitation & Boutiques',
                    'subtitle': 'Rayons, réserves, préparations, demandes',
                    'icon': 'fa fa-sitemap',
                    'action': actions['transfers'],
                    'tone': 'black',
                    'metrics': [
                        {'label': 'Commandes clients', 'value': sales_orders, 'format': 'number'},
                        {'label': 'Réceptions', 'value': pending_receipts, 'format': 'number'},
                        {'label': 'Réceptions', 'value': pending_receipts, 'format': 'number'},
                        {'label': 'Préparations', 'value': pending_deliveries, 'format': 'number'},
                    ],
                },
                {
                    'key': 'hr_admin',
                    'title': 'RH, Rapports & Administration',
                    'subtitle': 'Effectifs, rapports, audit, paramétrage',
                    'icon': 'fa fa-shield',
                    'action': 'primetech_reporting_center.action_hr_overview_dashboard',
                    'tone': 'white',
                    'metrics': [
                        {'label': 'Effectif', 'value': overview['hr']['employees'], 'format': 'number'},
                        {'label': 'Congés validés', 'value': overview['hr']['on_leave'], 'format': 'number'},
                        {'label': 'Rapports', 'value': 13, 'format': 'number'},
                        {'label': 'Audit système', 'value': 1, 'format': 'number'},
                    ],
                },
            ],
            'focus': [
                {'label': 'Solde courant caisses', 'value': overview['cash_registers']['current_balance'], 'format': 'currency', 'action': actions['finance']},
                {'label': 'Solde clôturé caisses', 'value': overview['cash_registers']['closing_balance'], 'format': 'currency', 'action': actions['finance']},
                {'label': 'Achats validés', 'value': overview['purchase_total'], 'format': 'currency', 'action': actions['purchase']},
                {'label': 'Congés validés', 'value': overview['hr']['on_leave'], 'format': 'number', 'action': 'primetech_reporting_center.action_hr_overview_dashboard'},
            ],
        }

    def _get_cashflow_analysis(self, open_model, filters=None, include_disbursement_accounts=False):
        """Return a decision-ready cashflow analysis for the executive board."""
        filters = filters or {}
        period_filters = self._scoped_period_filters(
            filters,
            'cashflow_period',
            filters.get('period', 'month'),
        )
        period = period_filters.get('period', 'month')
        start, end = self._get_period_bounds(period_filters)
        period_labels = {
            'today': _("Aujourd'hui"),
            'week': _('Cette semaine'),
            'month': _('Ce mois'),
            'quarter': _('Ce trimestre'),
            'year': _('Cette année'),
            'custom': _('Période sélectionnée'),
        }
        period_label = period_labels.get(period, _('Ce mois'))
        MoveLine = self.env['account.move.line']
        Payment = self.env['account.payment']
        Account = self.env['account.account']
        Journal = self.env['account.journal']
        period_domain = [
            ('parent_state', '=', 'posted'),
            ('date', '>=', start),
            ('date', '<=', end),
        ]

        # A payment is the authoritative source for manual and POS bank
        # payments. Its liquidity line can be an outstanding account rather
        # than the bank/cash account, so considering only ``asset_cash``
        # lines would omit valid incoming and outgoing payments.
        payment_domain = [
            ('date', '>=', start),
            ('date', '<=', end),
            ('state', 'in', ('in_process', 'paid')),
            ('move_id.state', '=', 'posted'),
        ]
        payments = Payment.search(payment_domain)
        payment_move_ids = set()
        clearing_account_ids = set()
        receipts = 0.0
        disbursements = 0.0
        receipt_move_ids = set()
        disbursement_move_ids = set()
        receipt_account_totals = defaultdict(lambda: {
            'amount': 0.0,
            'line_ids': set(),
            'line_count': 0,
        })
        disbursement_account_totals = defaultdict(lambda: {
            'amount': 0.0,
            'line_ids': set(),
            'line_count': 0,
        })

        def add_receipt_account(account, amount, line=False):
            if not account or amount <= 0:
                return
            account_total = receipt_account_totals[account.id]
            account_total['amount'] += amount
            if line and line.id:
                account_total['line_ids'].add(line.id)
            else:
                account_total['line_count'] += 1

        def add_disbursement_account(account, amount, line=False):
            if not include_disbursement_accounts or not account or amount <= 0:
                return
            account_total = disbursement_account_totals[account.id]
            account_total['amount'] += amount
            if line and line.id:
                account_total['line_ids'].add(line.id)
            else:
                account_total['line_count'] += 1

        for payment in payments:
            # Internal transfers only move money between the company's own
            # accounts. They are never an encaissement or a décaissement.
            is_internal_transfer = (
                'is_internal_transfer' in payment._fields
                and payment.is_internal_transfer
            ) or (
                'paired_internal_transfer_payment_id' in payment._fields
                and payment.paired_internal_transfer_payment_id
            ) or (
                'payment_type' in payment._fields
                and payment.payment_type == 'transfer'
            )
            if is_internal_transfer or not payment.move_id:
                continue

            payment_move_ids.add(payment.move_id.id)
            if payment.outstanding_account_id:
                clearing_account_ids.add(payment.outstanding_account_id.id)

            # This signed amount comes from the payment's actual liquidity
            # line and therefore remains correct for foreign currencies too.
            # Its category is determined by payment direction, never by the
            # counterpart entry of the double-entry move.
            amount = abs(payment.amount_company_currency_signed or 0.0)
            if not amount:
                amount = abs(payment.amount or 0.0)
            if payment.payment_type == 'inbound':
                receipts += amount
                receipt_move_ids.add(payment.move_id.id)
                receipt_lines = payment.move_id.line_ids.filtered(lambda line: (line.debit or 0.0) > 0)
                if payment.outstanding_account_id:
                    outstanding_lines = receipt_lines.filtered(
                        lambda line: line.account_id == payment.outstanding_account_id
                    )
                    receipt_lines = outstanding_lines or receipt_lines
                if receipt_lines:
                    for line in receipt_lines:
                        add_receipt_account(line.account_id, line.debit or 0.0, line)
                else:
                    add_receipt_account(payment.outstanding_account_id, amount)
            elif payment.payment_type == 'outbound':
                disbursements += amount
                disbursement_move_ids.add(payment.move_id.id)
                if include_disbursement_accounts:
                    disbursement_lines = payment.move_id.line_ids.filtered(lambda line: (line.credit or 0.0) > 0)
                    if payment.outstanding_account_id:
                        outstanding_lines = disbursement_lines.filtered(
                            lambda line: line.account_id == payment.outstanding_account_id
                        )
                        disbursement_lines = outstanding_lines or disbursement_lines
                    if disbursement_lines:
                        for line in disbursement_lines:
                            add_disbursement_account(line.account_id, line.credit or 0.0, line)
                    else:
                        add_disbursement_account(payment.outstanding_account_id, amount)

        # Add direct movements of bank/cash accounts: cash entries, POS cash
        # statement lines, and direct bank/cash journal entries. We aggregate
        # each accounting move before classifying it, so a double entry can
        # only enter one side of the cashflow.
        liquidity_account_ids = set(Account.search([('account_type', '=', 'asset_cash')]).ids)
        if 'default_account_id' in Journal._fields:
            liquidity_account_ids.update(
                Journal.search([('type', 'in', ('bank', 'cash'))]).mapped('default_account_id').ids
            )
        liquidity_account_ids = list(liquidity_account_ids)
        liquidity_domain = period_domain + [('account_id', 'in', liquidity_account_ids)]
        liquidity_lines = MoveLine.search(liquidity_domain) if liquidity_account_ids else MoveLine.browse()
        liquidity_by_move = defaultdict(lambda: {
            'debit': 0.0,
            'credit': 0.0,
            'lines': [],
        })
        for line in liquidity_lines:
            # These moves were already classified from account.payment above.
            # Ignoring them prevents double-counting manual and POS bank
            # payments that use the journal's actual liquidity line.
            if line.move_id.id in payment_move_ids:
                continue
            move_data = liquidity_by_move[line.move_id.id]
            move_data['debit'] += line.debit or 0.0
            move_data['credit'] += line.credit or 0.0
            move_data['lines'].append(line)

        for move_id, move_data in liquidity_by_move.items():
            move = self.env['account.move'].browse(move_id)
            payment = move.payment_id if 'payment_id' in move._fields else False
            # A payment outside the selected source set (for example an
            # internal transfer) must never be reintroduced by its lines.
            if payment:
                continue

            # Bank reconciliation transfers an amount from an outstanding
            # clearing account to the real bank account. The source payment
            # is already counted, therefore this settlement is excluded.
            counterpart_account_ids = set(move.line_ids.mapped('account_id').ids)
            counterpart_account_ids.difference_update(liquidity_account_ids)
            if clearing_account_ids.intersection(counterpart_account_ids):
                continue

            net_liquidity = move_data['debit'] - move_data['credit']
            if net_liquidity > 0.000001:
                receipts += net_liquidity
                receipt_move_ids.add(move_id)
                for line in move_data['lines']:
                    amount = (line.debit or 0.0) - (line.credit or 0.0)
                    if amount > 0:
                        add_receipt_account(line.account_id, amount, line)
            elif net_liquidity < -0.000001:
                disbursements += -net_liquidity
                disbursement_move_ids.add(move_id)
                if include_disbursement_accounts:
                    for line in move_data['lines']:
                        amount = (line.credit or 0.0) - (line.debit or 0.0)
                        if amount > 0:
                            add_disbursement_account(line.account_id, amount, line)

        receipt_move_ids = sorted(receipt_move_ids)
        disbursement_move_ids = sorted(disbursement_move_ids)
        cashflow_move_ids = sorted(set(receipt_move_ids) | set(disbursement_move_ids))
        receipt_domain = [('id', 'in', receipt_move_ids)]
        disbursement_domain = [('id', 'in', disbursement_move_ids)]
        classified_liquidity_domain = [('id', 'in', cashflow_move_ids)]

        expense_domain = period_domain + [('account_id.account_type', '=', 'expense')]
        expense_groups = MoveLine.read_group(expense_domain, ['debit', 'credit'], ['account_id'], lazy=False)
        expense_account_ids = [group['account_id'][0] for group in expense_groups if group.get('account_id')]
        # Expense account labels must match the French chart of accounts,
        # independently from the language used for the rest of the interface.
        expense_accounts_by_id = {
            account.id: account
            for account in Account.with_context(lang='fr_FR').browse(expense_account_ids)
        }
        expense_accounts = []
        for group in expense_groups:
            account_data = group.get('account_id')
            if not account_data:
                continue
            amount = (group.get('debit', 0.0) or 0.0) - (group.get('credit', 0.0) or 0.0)
            if amount <= 0:
                continue
            account = expense_accounts_by_id.get(account_data[0])
            if not account:
                continue
            expense_accounts.append({
                'id': account.id,
                'code': account.code or '',
                'name': account.name,
                'amount': amount,
                'line_count': group.get('__count', 0),
                'action': open_model(_('Charges — %s') % account.display_name, 'account.move.line', expense_domain + [('account_id', '=', account.id)]),
            })
        expense_accounts.sort(key=lambda row: row['amount'], reverse=True)
        total_expenses = sum(row['amount'] for row in expense_accounts)
        for row in expense_accounts:
            row['percent'] = row['amount'] * 100 / total_expenses if total_expenses else 0.0

        receipt_accounts_by_id = {
            account.id: account
            for account in Account.with_context(lang='fr_FR').browse(list(receipt_account_totals))
        }
        receipt_accounts = []
        for account_id, account_total in receipt_account_totals.items():
            account = receipt_accounts_by_id.get(account_id)
            amount = account_total['amount']
            if not account or amount <= 0:
                continue
            line_ids = sorted(account_total['line_ids'])
            receipt_accounts.append({
                'id': account.id,
                'code': account.code or '',
                'name': account.name,
                'amount': amount,
                'line_count': len(line_ids) or account_total['line_count'],
                'action': open_model(
                    _('Encaissements — %s') % account.display_name,
                    'account.move.line',
                    [('id', 'in', line_ids)] if line_ids else [('move_id', 'in', receipt_move_ids), ('account_id', '=', account.id)],
                ),
            })
        receipt_accounts.sort(key=lambda row: row['amount'], reverse=True)
        total_receipt_accounts = sum(row['amount'] for row in receipt_accounts)
        for row in receipt_accounts:
            row['percent'] = row['amount'] * 100 / total_receipt_accounts if total_receipt_accounts else 0.0

        disbursement_accounts = []
        if include_disbursement_accounts:
            disbursement_accounts_by_id = {
                account.id: account
                for account in Account.with_context(lang='fr_FR').browse(list(disbursement_account_totals))
            }
            for account_id, account_total in disbursement_account_totals.items():
                account = disbursement_accounts_by_id.get(account_id)
                amount = account_total['amount']
                if not account or amount <= 0:
                    continue
                line_ids = sorted(account_total['line_ids'])
                disbursement_accounts.append({
                    'id': account.id,
                    'code': account.code or '',
                    'name': account.name,
                    'amount': amount,
                    'line_count': len(line_ids) or account_total['line_count'],
                    'action': open_model(
                        _('Décaissements — %s') % account.display_name,
                        'account.move.line',
                        [('id', 'in', line_ids)] if line_ids else [('move_id', 'in', disbursement_move_ids), ('account_id', '=', account.id)],
                    ),
                })
            disbursement_accounts.sort(key=lambda row: row['amount'], reverse=True)
            total_disbursement_accounts = sum(row['amount'] for row in disbursement_accounts)
            for row in disbursement_accounts:
                row['percent'] = row['amount'] * 100 / total_disbursement_accounts if total_disbursement_accounts else 0.0

        net_cashflow = receipts - disbursements
        coverage_rate = receipts * 100 / disbursements if disbursements else 100.0
        return {
            'period': period,
            'period_label': period_label,
            'date_from': fields.Date.to_string(start),
            'date_to': fields.Date.to_string(end),
            'receipts': receipts,
            'disbursements': disbursements,
            'net_cashflow': net_cashflow,
            'coverage_rate': coverage_rate,
            'total_expenses': total_expenses,
            'all_expense_accounts': expense_accounts,
            'expense_accounts': expense_accounts[:5],
            'all_receipt_accounts': receipt_accounts,
            'receipt_accounts': receipt_accounts[:5],
            'all_disbursement_accounts': disbursement_accounts,
            'disbursement_accounts': disbursement_accounts[:5],
            'cashflow_action': open_model(_('Flux de trésorerie — %s') % period_label, 'account.move', classified_liquidity_domain, {'search_default_posted': 1}),
            'receipts_action': open_model(_('Encaissements — %s') % period_label, 'account.move', receipt_domain, {'search_default_posted': 1}),
            'disbursements_action': open_model(_('Décaissements — %s') % period_label, 'account.move', disbursement_domain, {'search_default_posted': 1}),
            'expenses_action': open_model(_('Comptes de charges — %s') % period_label, 'account.move.line', expense_domain),
        }

    def _get_cashflow_chart_by_date(self, start, end, chart_group):
        """Return actual receipts and disbursements grouped for the cashflow chart."""
        MoveLine = self.env['account.move.line']
        Payment = self.env['account.payment']
        Account = self.env['account.account']
        Journal = self.env['account.journal']
        values_by_key = defaultdict(lambda: {'income': 0.0, 'expense': 0.0})

        def key_for(value):
            value = fields.Date.to_date(value)
            return value.replace(day=1) if chart_group == 'month' else value

        payment_domain = [
            ('date', '>=', start),
            ('date', '<=', end),
            ('state', 'in', ('in_process', 'paid')),
            ('move_id.state', '=', 'posted'),
        ]
        payment_move_ids = set()
        clearing_account_ids = set()
        for payment in Payment.search(payment_domain):
            is_internal_transfer = (
                'is_internal_transfer' in payment._fields and payment.is_internal_transfer
            ) or (
                'paired_internal_transfer_payment_id' in payment._fields
                and payment.paired_internal_transfer_payment_id
            ) or (
                'payment_type' in payment._fields and payment.payment_type == 'transfer'
            )
            if is_internal_transfer or not payment.move_id:
                continue
            payment_move_ids.add(payment.move_id.id)
            if payment.outstanding_account_id:
                clearing_account_ids.add(payment.outstanding_account_id.id)
            amount = abs(payment.amount_company_currency_signed or 0.0) or abs(payment.amount or 0.0)
            if payment.payment_type == 'inbound':
                values_by_key[key_for(payment.date or payment.move_id.date)]['income'] += amount
            elif payment.payment_type == 'outbound':
                values_by_key[key_for(payment.date or payment.move_id.date)]['expense'] += amount

        liquidity_account_ids = set(Account.search([('account_type', '=', 'asset_cash')]).ids)
        if 'default_account_id' in Journal._fields:
            liquidity_account_ids.update(
                Journal.search([('type', 'in', ('bank', 'cash'))]).mapped('default_account_id').ids
            )
        if not liquidity_account_ids:
            return values_by_key

        liquidity_domain = [
            ('parent_state', '=', 'posted'),
            ('date', '>=', start),
            ('date', '<=', end),
            ('account_id', 'in', list(liquidity_account_ids)),
        ]
        liquidity_by_move = defaultdict(lambda: {'debit': 0.0, 'credit': 0.0})
        for line in MoveLine.search(liquidity_domain):
            if line.move_id.id in payment_move_ids:
                continue
            move_data = liquidity_by_move[line.move_id.id]
            move_data['debit'] += line.debit or 0.0
            move_data['credit'] += line.credit or 0.0

        for move_id, move_data in liquidity_by_move.items():
            move = self.env['account.move'].browse(move_id)
            payment = move.payment_id if 'payment_id' in move._fields else False
            if payment:
                continue
            counterpart_account_ids = set(move.line_ids.mapped('account_id').ids)
            counterpart_account_ids.difference_update(liquidity_account_ids)
            if clearing_account_ids.intersection(counterpart_account_ids):
                continue
            net_liquidity = move_data['debit'] - move_data['credit']
            if net_liquidity > 0.000001:
                values_by_key[key_for(move.date)]['income'] += net_liquidity
            elif net_liquidity < -0.000001:
                values_by_key[key_for(move.date)]['expense'] += -net_liquidity
        return values_by_key

    @api.model
    def get_cashflow_report_data(self, filters=None):
        """Prepare the complete treasury report for the executive dashboard."""
        filters = dict(filters or {})

        def open_model(name, model, domain=None, context=None, views=None):
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': model,
                'domain': domain or [],
                'context': context or {},
                'view_mode': views or 'list,form',
            }

        analysis = self._get_cashflow_analysis(
            open_model, filters, include_disbursement_accounts=True
        )
        start = fields.Date.to_date(analysis['date_from'])
        end = fields.Date.to_date(analysis['date_to'])
        MoveLine = self.env['account.move.line']
        period_domain = [
            ('parent_state', '=', 'posted'),
            ('date', '>=', start),
            ('date', '<=', end),
        ]

        def account_type_balance(account_types, direction):
            groups = MoveLine.read_group(
                period_domain + [('account_id.account_type', 'in', account_types)],
                ['debit', 'credit'],
                [],
            )
            values = groups[0] if groups else {}
            debit = values.get('debit', 0.0) or 0.0
            credit = values.get('credit', 0.0) or 0.0
            return credit - debit if direction == 'credit' else debit - credit

        operating_income = account_type_balance(['income', 'income_other'], 'credit')
        operating_expenses = account_type_balance(
            ['expense', 'expense_depreciation', 'expense_direct_cost'], 'debit'
        )
        cashflow_move_ids = []
        for domain_item in analysis.get('cashflow_action', {}).get('domain', []):
            if domain_item[:2] == ('id', 'in'):
                cashflow_move_ids = domain_item[2]
                break
        return {
            'company': self.env.company,
            'analysis': analysis,
            'receipt_accounts': analysis['all_receipt_accounts'],
            'disbursement_accounts': analysis['all_disbursement_accounts'],
            'expense_accounts': analysis['all_expense_accounts'],
            'cashflow_move_count': len(cashflow_move_ids),
            'operating_result': {
                'income': operating_income,
                'expenses': operating_expenses,
                'result': operating_income - operating_expenses,
            },
            'generated_at': fields.Datetime.context_timestamp(
                self.env.user, fields.Datetime.now()
            ).strftime('%d/%m/%Y %H:%M'),
        }

    @api.model
    def get_cashflow_print_action(self, filters=None):
        """Return the PDF report action for the currently selected KPI period."""
        return self.env.ref(
            'primetech_reporting_center.action_executive_cashflow_pdf'
        ).report_action(self.env.company, data={'filters': dict(filters or {})})

    def _get_dashboard_preview_action(self, title, report_xmlid, payload):
        """Render the preview through the same QWeb pipeline as the PDF."""
        company = self.env.company
        report = self.env.ref(report_xmlid)
        rendered = self.env['ir.actions.report']._render_qweb_html(
            report.report_name, [company.id], data=payload
        )
        html = rendered[0] if isinstance(rendered, tuple) else rendered
        if isinstance(html, bytes):
            html = html.decode()
        preview = self.env['pt.dashboard.report.preview.wizard'].create({
            'name': title,
            'html_content': html,
            'report_xmlid': report_xmlid,
            'report_payload': json.dumps(payload, default=str),
        })
        view_id = self.env.ref(
            'primetech_reporting_center.view_dashboard_report_preview_wizard'
        ).id
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': preview._name,
            'view_mode': 'form',
            'view_id': view_id,
            # The action service preprocesses ``views`` before opening a
            # window action. Supplying it explicitly avoids the undefined
            # map error raised by a bare view_mode/view_id payload.
            'views': [[view_id, 'form']],
            'res_id': preview.id,
            'target': 'current',
        }

    @api.model
    def get_cashflow_preview_action(self, filters=None):
        """Build the treasury preview only when the user explicitly requests it."""
        filters = dict(filters or {})
        return self._get_dashboard_preview_action(
            _('Aperçu — rapport de suivi de trésorerie'),
            'primetech_reporting_center.action_executive_cashflow_pdf',
            {'filters': filters},
        )

    def _prepare_top_watch_report_rows(self, rows):
        """Keep only report-safe values from the dashboard's current watch list."""
        prepared_rows = []
        for row in (rows or [])[:30]:
            if not isinstance(row, dict):
                continue
            try:
                stock = float(row.get('stock') or 0.0)
                rotation = float(row.get('rotation') or 0.0)
            except (TypeError, ValueError):
                continue
            status_tone = str(row.get('status_tone') or 'warning')
            if status_tone not in ('danger', 'critical', 'warning'):
                status_tone = 'warning'
            prepared_rows.append({
                'product': str(row.get('product') or '-'),
                'rayon': str(row.get('rayon') or '-'),
                'status': str(row.get('status') or _('À surveiller')),
                'status_tone': status_tone,
                'stock': stock,
                'rotation': rotation,
            })
        return prepared_rows

    @api.model
    def get_top_watch_report_data(self, filters=None, rows=None):
        """Prepare the report from the same rows currently displayed by the KPI."""
        filters = dict(filters or {})
        period_filters = self._scoped_period_filters(filters, 'top_watch_period', 'month')
        start, end = self._get_period_bounds(period_filters)
        prepared_rows = self._prepare_top_watch_report_rows(rows)
        if rows is None:
            # This fallback keeps the report usable outside the dashboard action.
            prepared_rows = self._prepare_top_watch_report_rows(
                self.get_executive_board(filters).get('top_watch', [])
            )
        status_counts = defaultdict(int)
        for row in prepared_rows:
            status_counts[row['status_tone']] += 1
        return {
            'company': self.env.company,
            'date_from': fields.Date.to_string(start),
            'date_to': fields.Date.to_string(end),
            'rows': prepared_rows,
            'total_products': len(prepared_rows),
            'out_of_stock_count': status_counts['danger'],
            'critical_count': status_counts['critical'],
            'minimum_count': status_counts['warning'],
            'total_rotation': sum(row['rotation'] for row in prepared_rows),
            'generated_at': fields.Datetime.context_timestamp(
                self.env.user, fields.Datetime.now()
            ).strftime('%d/%m/%Y %H:%M'),
        }

    @api.model
    def get_top_watch_print_action(self, filters=None, rows=None):
        """Return the stock-watch PDF action for the selected KPI period."""
        return self.env.ref(
            'primetech_reporting_center.action_executive_top_watch_pdf'
        ).report_action(self.env.company, data={
            'filters': dict(filters or {}),
            'rows': self._prepare_top_watch_report_rows(rows),
        })

    @api.model
    def get_top_watch_preview_action(self, filters=None, rows=None):
        """Open the stock-watch report preview from the KPI's current rows."""
        filters = dict(filters or {})
        prepared_rows = self._prepare_top_watch_report_rows(rows)
        return self._get_dashboard_preview_action(
            _('Aperçu — top produits à surveiller'),
            'primetech_reporting_center.action_executive_top_watch_pdf',
            {'filters': filters, 'rows': prepared_rows},
        )

    def _prepare_partner_balance_report_rows(self, rows):
        """Keep the exact visible partner-list rows, without their UI actions."""
        prepared_rows = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            try:
                debit = float(row.get('debit') or 0.0)
                credit = float(row.get('credit') or 0.0)
                balance = float(row.get('balance') or 0.0)
            except (TypeError, ValueError):
                continue
            status_class = str(row.get('status_class') or 'warn')
            if status_class not in ('ok', 'warn', 'danger'):
                status_class = 'warn'
            prepared_rows.append({
                'partner': str(row.get('partner') or '-'),
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'status': str(row.get('status') or _('À vérifier')),
                'status_class': status_class,
            })
        return prepared_rows

    @api.model
    def get_partner_balance_report_data(self, partner_type, rows=None, summary=None):
        """Prepare a report for the precise client or supplier rows on screen."""
        partner_type = 'suppliers' if partner_type == 'suppliers' else 'customers'
        summary = summary if isinstance(summary, dict) else {}
        prepared_rows = self._prepare_partner_balance_report_rows(rows)
        try:
            global_total = float(summary.get('total') or 0.0)
            filtered_count = int(summary.get('filtered_count') or 0)
        except (TypeError, ValueError):
            global_total = 0.0
            filtered_count = 0
        labels = {
            'customers': {
                'title': _('Rapport des créances clients'),
                'total_label': _('Total solde débiteur'),
                'partner_label': _('Client'),
                'filter_label': _('Créances clients'),
            },
            'suppliers': {
                'title': _('Rapport des créances fournisseurs'),
                'total_label': _('Total solde créditeur'),
                'partner_label': _('Fournisseur'),
                'filter_label': _('Créances fournisseurs'),
            },
        }[partner_type]
        filter_labels = {
            'all': _('Tous les soldes'),
            'high': _('Soldes élevés'),
            'with_debit': _('Avec débits'),
            'with_credit': _('Avec crédits / règlements'),
            'without_payment': _('Sans règlement'),
        }
        filter_key = str(summary.get('filter') or 'all')
        return {
            'company': self.env.company,
            'partner_type': partner_type,
            'title': labels['title'],
            'total_label': labels['total_label'],
            'partner_label': labels['partner_label'],
            'filter_label': labels['filter_label'],
            'criteria_label': filter_labels.get(filter_key, filter_labels['all']),
            'search_term': str(summary.get('search_term') or '').strip(),
            'rows': prepared_rows,
            'displayed_count': len(prepared_rows),
            'filtered_count': max(filtered_count, len(prepared_rows)),
            'global_total': global_total,
            'displayed_total': sum(row['balance'] for row in prepared_rows),
            'total_debit': sum(row['debit'] for row in prepared_rows),
            'total_credit': sum(row['credit'] for row in prepared_rows),
            'generated_at': fields.Datetime.context_timestamp(
                self.env.user, fields.Datetime.now()
            ).strftime('%d/%m/%Y %H:%M'),
        }

    @api.model
    def get_partner_balance_print_action(self, partner_type, rows=None, summary=None):
        """Return the PDF for the currently displayed partner-balance rows."""
        partner_type = 'suppliers' if partner_type == 'suppliers' else 'customers'
        prepared_rows = self._prepare_partner_balance_report_rows(rows)
        safe_summary = summary if isinstance(summary, dict) else {}
        return self.env.ref(
            'primetech_reporting_center.action_executive_partner_balance_pdf'
        ).report_action(self.env.company, data={
            'partner_type': partner_type,
            'rows': prepared_rows,
            'summary': safe_summary,
        })

    @api.model
    def get_partner_balance_preview_action(self, partner_type, rows=None, summary=None):
        """Open an HTML preview for the precise list visible in the KPI."""
        partner_type = 'suppliers' if partner_type == 'suppliers' else 'customers'
        prepared_rows = self._prepare_partner_balance_report_rows(rows)
        safe_summary = summary if isinstance(summary, dict) else {}
        preview_title = (
            _('Aperçu — rapport des créances fournisseurs')
            if partner_type == 'suppliers'
            else _('Aperçu — rapport des créances clients')
        )
        return self._get_dashboard_preview_action(
            preview_title,
            'primetech_reporting_center.action_executive_partner_balance_pdf',
            {
                'partner_type': partner_type,
                'rows': prepared_rows,
                'summary': safe_summary,
            },
        )

    @api.model
    def get_executive_board(self, filters=None):
        filters = filters or {}
        overview = self.get_executive_overview(filters)
        StockPicking = self.env['stock.picking']
        Product = self.env['product.product']
        ProductTemplate = self.env['product.template']

        def open_model(name, model, domain=None, context=None, views=None):
            view_mode = views or 'list,form'
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': model,
                'view_mode': view_mode,
                'views': [[False, mode] for mode in view_mode.split(',')],
                'domain': domain or [],
                'context': context or {},
            }

        cashflow_analysis = self._get_cashflow_analysis(open_model, filters)
        selected_period = filters.get('period', 'month')
        period_labels = {'today': "Aujourd'hui", 'week': 'Cette semaine', 'month': 'Ce mois', 'quarter': 'Ce trimestre', 'year': 'Cette année', 'custom': 'Période sélectionnée'}
        period_label = period_labels.get(selected_period, 'Ce mois')
        store_period = self._period_filter_value(filters, 'store_period', selected_period)
        revenue_period = self._period_filter_value(filters, 'revenue_period', selected_period)
        top_watch_period = self._period_filter_value(filters, 'top_watch_period', 'month')
        store_label = period_labels.get(store_period, period_label)
        revenue_label = period_labels.get(revenue_period, period_label)
        start, end = self._get_period_bounds(filters)
        period_datetime_domain = [
            ('date_order', '>=', fields.Datetime.to_datetime(start)),
            ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
        ]
        revenue_period_filters = self._scoped_period_filters(filters, 'revenue_period', selected_period)
        revenue_start, revenue_end = self._get_period_bounds(revenue_period_filters)
        top_watch_start, top_watch_end = self._get_period_bounds(
            self._scoped_period_filters(filters, 'top_watch_period', top_watch_period)
        )
        top_watch_order_datetime_domain = [
            ('order_id.date_order', '>=', fields.Datetime.to_datetime(top_watch_start)),
            ('order_id.date_order', '<', fields.Datetime.to_datetime(top_watch_end) + timedelta(days=1)),
        ]
        sale_report_domain = [('date', '>=', start), ('date', '<=', end)]
        actions = {
            'sales': open_model(
                'Analyse du chiffre d\'affaires',
                'sale.report',
                sale_report_domain,
                {'group_by': ['date:year', 'date:month', 'date:day']},
                'pivot,graph,list',
            ),
            'finance': open_model('Situation financière', 'account.move', [], {'search_default_posted': 1}),
            'purchase': open_model('Commandes fournisseurs', 'purchase.order', [('state', 'in', ['purchase', 'done'])] + period_datetime_domain),
            'stock': open_model('Stocks disponibles', 'stock.quant', [('location_id.usage', '=', 'internal')]),
            'transfers': open_model('Bons de transfert', 'stock.picking', []),
            'products': open_model('Produits', 'product.template', []),
        }
        if 'pos.order' in self.env.registry:
            actions['pos'] = open_model('Ventes PDV', 'pos.order', period_datetime_domain)
        else:
            actions['pos'] = actions['sales']
        if 'pos.session' in self.env.registry:
            actions['pos_sessions'] = open_model('Sessions de caisse', 'pos.session', [])
        else:
            actions['pos_sessions'] = actions['pos']
        if 'hr.employee' in self.env.registry:
            actions['hr'] = open_model('Employés', 'hr.employee', [])
        else:
            actions['hr'] = actions['finance']

        receivable_kpis = self._get_partner_balance_kpis(open_model, filters)
        bank_period_filters = dict(filters, period=filters.get('period', 'month'))
        banks = []
        for journal in self.env['account.journal'].search([('type', 'in', ('bank', 'cash'))]):
            journal_line_domain = [('journal_id', '=', journal.id), ('parent_state', '=', 'posted')] + self._get_date_domain(bank_period_filters, 'date')
            if journal.default_account_id:
                journal_line_domain.append(('account_id', '=', journal.default_account_id.id))
            journal_lines = self.env['account.move.line'].search(journal_line_domain)
            balance = sum(journal_lines.mapped('balance'))
            if balance <= 0:
                continue
            banks.append({
                'id': journal.id,
                'name': journal.display_name,
                'category': self._categorize_journal(journal),
                'balance': balance,
                'action': open_model(journal.display_name, 'account.move.line', journal_line_domain),
            })
        if 'pos.payment' in self.env.registry:
            pos_payment_domain = [
                ('pos_order_id.state', 'in', ('paid', 'done', 'invoiced')),
            ] + self._get_date_domain(bank_period_filters, 'payment_date')
            for group in self.env['pos.payment'].read_group(
                pos_payment_domain,
                ['amount:sum'],
                ['payment_method_id'],
                lazy=False,
            ):
                payment_method = group.get('payment_method_id')
                if not payment_method:
                    continue
                method_id, method_name = payment_method
                payment_total = group.get('amount', 0.0)
                if payment_total <= 0:
                    continue
                method_domain = pos_payment_domain + [('payment_method_id', '=', method_id)]
                banks.append({
                    'id': f'pos-payment-{method_id}',
                    'name': f'PDV — {method_name}',
                    'category': 'Point de vente',
                    'balance': payment_total,
                    'action': open_model(f'Paiements PDV — {method_name}', 'pos.payment', method_domain),
                })
        billing_period = self._period_filter_value(filters, 'billing_period', filters.get('period', 'month'))
        billing_filters = self._scoped_period_filters(filters, 'billing_period', filters.get('period', 'month'))
        invoice_domain_all = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')] + self._get_date_domain(billing_filters, 'invoice_date')
        posted_invoices = self.env['account.move'].search(invoice_domain_all)
        billing_total = sum(posted_invoices.mapped('amount_total'))
        billing_balance = sum(posted_invoices.mapped('amount_residual'))
        billing_paid = billing_total - billing_balance
        unpaid_invoice_domain = invoice_domain_all + [('payment_state', 'in', ['not_paid', 'partial'])]
        unpaid_invoice_count = self.env['account.move'].search_count(unpaid_invoice_domain)
        billing_count = len(posted_invoices)
        billing = {
            'period': billing_period,
            'total': billing_total,
            'paid': billing_paid,
            'balance': billing_balance,
            'count': billing_count,
            'unpaid_count': unpaid_invoice_count,
            'unpaid_rate': (billing_balance / billing_total * 100 if billing_total else 0),
            'action': open_model('Factures clients', 'account.move', invoice_domain_all, {'search_default_posted': 1}),
            'payments_action': open_model('Factures clients encaissées', 'account.move', invoice_domain_all + [('payment_state', 'in', ['paid', 'in_payment'])], {'search_default_posted': 1}),
            'unpaid_action': open_model('Factures clients impayées', 'account.move', unpaid_invoice_domain, {'search_default_posted': 1}),
        }
        global_invoice_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ] + self._get_date_domain(filters, 'invoice_date')
        global_invoices = self.env['account.move'].search(global_invoice_domain)
        global_invoice_total = sum(global_invoices.mapped('amount_total'))
        global_receivable_total = sum(global_invoices.mapped('amount_residual'))
        confirmed_purchase_domain = [
            ('state', 'in', ['purchase', 'done']),
        ] + period_datetime_domain
        purchase_group = self.env['purchase.order'].read_group(confirmed_purchase_domain, ['amount_total'], [])
        purchase_total_confirmed = purchase_group[0].get('amount_total', 0.0) if purchase_group else 0.0
        supplier_bill_domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
        ] + self._get_date_domain(filters, 'invoice_date')
        supplier_bill_group = self.env['account.move'].read_group(supplier_bill_domain, ['amount_total', 'amount_residual'], [])
        supplier_bill_total = supplier_bill_group[0].get('amount_total', 0.0) if supplier_bill_group else 0.0
        supplier_debt_total = supplier_bill_group[0].get('amount_residual', 0.0) if supplier_bill_group else 0.0
        supplier_unpaid_count = self.env['account.move'].search_count(supplier_bill_domain + [('amount_residual', '>', 0)])
        supplier_payment_domain = [
            ('payment_type', '=', 'outbound'),
            ('state', 'not in', ['draft', 'cancel', 'cancelled', 'rejected']),
        ] + self._get_date_domain(filters, 'date')
        supplier_payment_group = self.env['account.payment'].read_group(supplier_payment_domain, ['amount'], [])
        supplier_payment_total = supplier_payment_group[0].get('amount', 0.0) if supplier_payment_group else 0.0
        supplier_bill_paid_total = supplier_bill_total - supplier_debt_total
        supplier_payment_total = max(supplier_payment_total, supplier_bill_paid_total)
        period_purchase_orders = self.env['purchase.order'].search(confirmed_purchase_domain)
        active_supplier_ids = set(period_purchase_orders.mapped('partner_id').ids)
        active_supplier_ids.update(self.env['account.move'].search(supplier_bill_domain).mapped('partner_id').ids)
        supplier_action_domain = [('id', 'in', list(active_supplier_ids))]
        supplier_action = open_model('Fournisseurs actifs sur la période', 'res.partner', supplier_action_domain)
        supplier_bills_action = open_model('Factures fournisseurs', 'account.move', supplier_bill_domain, {'search_default_posted': 1})
        supplier_payments_action = open_model('Paiements fournisseurs', 'account.payment', supplier_payment_domain)
        cash_lines = overview['cash_registers']['sessions']
        if not cash_lines:
            cash_lines = [{'name': 'Aucune caisse', 'state': '-', 'user': '-', 'cashier': '-', 'opening_date': '-', 'balance': 0, 'current_balance': 0, 'closing_balance': 0, 'orders_total': 0, 'status_class': 'muted', 'action': actions['pos_sessions']}]
        else:
            for line in cash_lines:
                line['action'] = open_model('Session de caisse', 'pos.session', [('id', '=', line['id'])])
        stock_scope = self._period_filter_value(filters, 'stock_scope', 'all')
        template_base_domain = []
        if stock_scope == 'sale':
            template_base_domain.append(('sale_ok', '=', True))
        elif stock_scope == 'purchase':
            template_base_domain.append(('purchase_ok', '=', True))
        template_count = ProductTemplate.search_count(template_base_domain)
        scoped_product_domain = []
        if template_base_domain:
            scoped_template_ids = ProductTemplate.search(template_base_domain).ids
            if not scoped_template_ids:
                template_base_domain = []
                template_count = ProductTemplate.search_count(template_base_domain)
            else:
                scoped_product_domain = [('product_tmpl_id', 'in', scoped_template_ids)]
        product_action = open_model('Produits stockables', 'product.template', template_base_domain)
        internal_quant_domain = [('location_id.usage', '=', 'internal')]
        if scoped_product_domain:
            scoped_product_ids = Product.search(scoped_product_domain).ids
            internal_quant_domain.append(('product_id', 'in', scoped_product_ids))
        Quant = self.env['stock.quant']
        quant_value_field = 'value' if 'value' in Quant._fields else 'inventory_value' if 'inventory_value' in Quant._fields else None
        quant_fields = ['quantity'] + ([quant_value_field] if quant_value_field else [])
        quant_groups = Quant.read_group(internal_quant_domain, quant_fields, ['product_id'], lazy=False)
        grouped_product_ids = [group['product_id'][0] for group in quant_groups if group.get('product_id')]
        grouped_products = Product.browse(grouped_product_ids)
        product_by_id = {product.id: product for product in grouped_products}
        qty_by_template = defaultdict(float)
        value_by_template = defaultdict(float)
        for group in quant_groups:
            product_data = group.get('product_id')
            if not product_data:
                continue
            product = product_by_id.get(product_data[0])
            if not product:
                continue
            template = product.product_tmpl_id
            quantity = group.get('quantity', 0.0) or 0.0
            qty_by_template[template.id] += quantity
            unit_cost = product.standard_price or template.standard_price or template.list_price or 0.0
            quant_value = group.get(quant_value_field, 0.0) if quant_value_field else 0.0
            value_by_template[template.id] += quant_value or quantity * unit_cost
        stock_value = sum(value_by_template.values())
        positive_template_ids = {template_id for template_id, quantity in qty_by_template.items() if quantity > 0}
        out_count = max(template_count - len(positive_template_ids), 0)
        settings = self.env['primetech.reporting.settings'].get_values()
        min_qty = settings['stock_min_alert_threshold']
        max_qty = settings['stock_overstock_threshold']
        min_template_ids = [template_id for template_id, quantity in qty_by_template.items() if 0 < quantity <= min_qty]
        over_template_ids = [template_id for template_id, quantity in qty_by_template.items() if quantity >= max_qty]
        min_count = len(min_template_ids)
        over_count = len(over_template_ids)
        out_domain = template_base_domain + [('qty_available', '<=', 0)]
        min_domain = template_base_domain + [('qty_available', '>', 0), ('qty_available', '<=', min_qty)]
        over_domain = template_base_domain + [('qty_available', '>=', max_qty)]
        out_action = open_model('Produits en rupture', 'product.template', out_domain)
        min_action = open_model('Produits sous stock minimum', 'product.template', min_domain)
        over_action = open_model('Produits en surstock', 'product.template', over_domain)
        categories_payload = self._get_revenue_categories_payload(revenue_period_filters, open_model)

        store_payload = self._get_store_kpi_payload(filters)
        stores = store_payload['stores']
        store_summary = store_payload['store_summary']

        # Revenue and category data share one global-sales source (confirmed
        # commercial sales plus completed POS sales), never cash movements.
        revenue_payload = self._get_revenue_kpi_payload(filters)
        revenue_chart = revenue_payload['revenue_chart']
        categories_payload = revenue_payload['categories']
        vehicles = []
        if 'fleet.vehicle' in self.env.registry:
            for vehicle in self.env['fleet.vehicle'].search([], limit=10):
                status = vehicle.state_id.name if vehicle.state_id else 'Disponible'
                vehicles.append({
                    'vehicle': vehicle.license_plate or vehicle.name or '-',
                    'type': vehicle.model_id.name if vehicle.model_id else '-',
                    'status': status,
                    'availability': 'Disponible' if status.lower() in ('disponible', 'registered') else status,
                    'action': open_model('Véhicule', 'fleet.vehicle', [('id', '=', vehicle.id)]),
                })
        if not vehicles:
            vehicles = [{'vehicle': '-', 'type': '-', 'status': 'Aucun véhicule', 'availability': '-'}]

        def count_action_item(label, model, domain, action_name=None):
            return {
                'label': label,
                'count': self.env[model].search_count(domain),
                'action': open_model(action_name or label, model, domain),
            }

        procurement_items = [
            count_action_item('En attente', 'purchase.order', [('state', 'in', ['draft', 'sent', 'to approve'])], 'Demandes d’approvisionnement en attente'),
            count_action_item('Validées', 'purchase.order', [('state', 'in', ['purchase', 'done'])], 'Demandes d’approvisionnement validées'),
            count_action_item('En préparation', 'stock.picking', [('picking_type_id.code', '=', 'incoming'), ('state', 'in', ['confirmed', 'assigned'])], 'Réceptions fournisseurs en préparation'),
            count_action_item('Expédiées', 'stock.picking', [('picking_type_id.code', '=', 'incoming'), ('state', 'in', ['waiting', 'confirmed', 'assigned'])], 'Réceptions fournisseurs attendues'),
            count_action_item('Réceptionnées', 'stock.picking', [('picking_type_id.code', '=', 'incoming'), ('state', '=', 'done')], 'Réceptions fournisseurs terminées'),
        ]
        transfer_items = [
            count_action_item('En attente', 'stock.picking', [('picking_type_id.code', '=', 'internal'), ('state', 'in', ['draft', 'waiting'])], 'Transferts en attente'),
            count_action_item('En préparation', 'stock.picking', [('picking_type_id.code', '=', 'internal'), ('state', '=', 'confirmed')], 'Transferts en préparation'),
            count_action_item('En cours', 'stock.picking', [('picking_type_id.code', '=', 'internal'), ('state', '=', 'assigned')], 'Transferts en cours'),
            count_action_item('Expédiés', 'stock.picking', [('picking_type_id.code', '=', 'internal'), ('state', 'in', ['assigned'])], 'Transferts expédiés'),
            count_action_item('Réceptionnés', 'stock.picking', [('picking_type_id.code', '=', 'internal'), ('state', '=', 'done')], 'Transferts réceptionnés'),
        ]
        customer_items = [
            count_action_item('À préparer', 'stock.picking', [('picking_type_id.code', '=', 'outgoing'), ('state', '=', 'confirmed')], 'Commandes clients à préparer'),
            count_action_item('En préparation', 'stock.picking', [('picking_type_id.code', '=', 'outgoing'), ('state', '=', 'assigned')], 'Commandes clients en préparation'),
            count_action_item('En cours livraison', 'stock.picking', [('picking_type_id.code', '=', 'outgoing'), ('state', 'in', ['waiting', 'assigned'])], 'Commandes clients en livraison'),
            count_action_item('Livrées', 'stock.picking', [('picking_type_id.code', '=', 'outgoing'), ('state', '=', 'done')], 'Commandes clients livrées'),
        ]

        logistics_colors = {
            'success': '#16a34a',
            'info': '#2f80ed',
            'primary': '#6366f1',
            'warning': '#f59e0b',
            'danger': '#e11d48',
            'muted': '#cbd5e1',
        }

        def decorate_logistics_items(items, styles):
            """Add a visual priority and an accurate share to each workflow step."""
            total = sum(item['count'] for item in items)
            cursor = 0.0
            gradient_parts = []
            for item in items:
                tone, indicator = styles.get(item['label'], ('muted', _('Sans activité')))
                share = item['count'] * 100 / total if total else 0.0
                item.update({
                    'tone': tone,
                    'indicator': indicator,
                    'percent': round(share, 1),
                })
                if share:
                    color = logistics_colors[tone]
                    gradient_parts.append(f'{color} {cursor:.2f}% {cursor + share:.2f}%')
                    cursor += share
            return {
                'total': total,
                'items': items,
                'donut_style': 'background: conic-gradient(%s)' % (
                    ', '.join(gradient_parts) if gradient_parts else '#e8eef6 0 100%'
                ),
            }

        supply_requests = decorate_logistics_items(procurement_items, {
            'En attente': ('warning', _('À valider')),
            'Validées': ('info', _('Confirmées')),
            'En préparation': ('primary', _('Réception à suivre')),
            'Expédiées': ('info', _('En transit')),
            'Réceptionnées': ('success', _('Terminées')),
        })
        supply_transfers = decorate_logistics_items(transfer_items, {
            'En attente': ('warning', _('À lancer')),
            'En préparation': ('primary', _('En traitement')),
            'En cours': ('info', _('En mouvement')),
            'Expédiés': ('info', _('En transit')),
            'Réceptionnés': ('success', _('Terminés')),
        })
        supply_customers = decorate_logistics_items(customer_items, {
            'À préparer': ('warning', _('À préparer')),
            'En préparation': ('primary', _('En traitement')),
            'En cours livraison': ('info', _('En livraison')),
            'Livrées': ('success', _('Terminées')),
        })
        purchase_pending_count = procurement_items[0]['count']
        transfer_pending_count = sum(item['count'] for item in transfer_items if item['label'] != 'Réceptionnés')

        expiry_template_ids = []
        if 'stock.lot' in self.env.registry:
            Lot = self.env['stock.lot']
            expiry_field = 'expiration_date' if 'expiration_date' in Lot._fields else 'life_date' if 'life_date' in Lot._fields else None
            if expiry_field:
                expiry_limit = fields.Date.today() + timedelta(days=30)
                expiry_lots = Lot.search([(expiry_field, '!=', False), (expiry_field, '<=', expiry_limit), ('product_id.product_tmpl_id', 'in', list(qty_by_template.keys()))])
                expiry_template_ids = list(set(expiry_lots.mapped('product_id.product_tmpl_id').ids))
        recent_move_template_ids = set(self.env['stock.move'].search([
            ('state', '=', 'done'),
            ('date', '>=', fields.Datetime.subtract(fields.Datetime.now(), days=90)),
            ('product_id.product_tmpl_id', 'in', list(qty_by_template.keys())),
        ]).mapped('product_id.product_tmpl_id').ids)
        slow_template_ids = [template_id for template_id, quantity in qty_by_template.items() if quantity > 0 and template_id not in recent_move_template_ids]
        expiry_action = open_model('Produits proches péremption', 'product.template', [('id', 'in', expiry_template_ids)])
        slow_action = open_model('Articles à faible rotation', 'product.template', [('id', 'in', slow_template_ids)])

        sold_qty_by_template = defaultdict(float)
        if 'sale.order.line' in self.env.registry:
            sale_groups = self.env['sale.order.line'].read_group(
                [('order_id.state', 'in', ['sale', 'done'])] + top_watch_order_datetime_domain + [('product_id', '!=', False)],
                ['product_uom_qty'],
                ['product_id'],
                lazy=False,
            )
            sale_products = Product.browse([group['product_id'][0] for group in sale_groups if group.get('product_id')])
            sale_product_by_id = {product.id: product for product in sale_products}
            for group in sale_groups:
                product_data = group.get('product_id')
                product = sale_product_by_id.get(product_data[0]) if product_data else False
                if product:
                    sold_qty_by_template[product.product_tmpl_id.id] += group.get('product_uom_qty', 0.0) or 0.0
        invoice_groups = self.env['account.move.line'].read_group(
            [('move_id.move_type', '=', 'out_invoice'), ('move_id.state', '=', 'posted'), ('move_id.invoice_date', '>=', top_watch_start), ('move_id.invoice_date', '<=', top_watch_end), ('product_id', '!=', False)],
            ['quantity'],
            ['product_id'],
            lazy=False,
        )
        invoice_products = Product.browse([group['product_id'][0] for group in invoice_groups if group.get('product_id')])
        invoice_product_by_id = {product.id: product for product in invoice_products}
        for group in invoice_groups:
            product_data = group.get('product_id')
            product = invoice_product_by_id.get(product_data[0]) if product_data else False
            if product:
                sold_qty_by_template[product.product_tmpl_id.id] += group.get('quantity', 0.0) or 0.0
        if 'pos.order.line' in self.env.registry:
            pos_groups = self.env['pos.order.line'].read_group(
                top_watch_order_datetime_domain + [('product_id', '!=', False)],
                ['qty'],
                ['product_id'],
                lazy=False,
            )
            pos_products = Product.browse([group['product_id'][0] for group in pos_groups if group.get('product_id')])
            pos_product_by_id = {product.id: product for product in pos_products}
            for group in pos_groups:
                product_data = group.get('product_id')
                product = pos_product_by_id.get(product_data[0]) if product_data else False
                if product:
                    sold_qty_by_template[product.product_tmpl_id.id] += group.get('qty', 0.0) or 0.0

        watch_candidates = []
        for template_id, sold_qty in sorted(sold_qty_by_template.items(), key=lambda item: item[1], reverse=True):
            stock_qty = qty_by_template.get(template_id, ProductTemplate.browse(template_id).qty_available)
            # The watch list is intentionally reserved for products with
            # meaningful sales whose available quantity has reached the
            # configured minimum threshold.  Sorting by sales gives high
            # rotation products priority over slower ones at the same stock level.
            if sold_qty <= 0 or stock_qty > min_qty:
                continue
            template = ProductTemplate.browse(template_id)
            if stock_qty <= 0:
                status = 'Rupture'
                status_tone = 'danger'
            elif stock_qty <= min_qty * 0.5:
                status = 'Stock critique'
                status_tone = 'critical'
            else:
                status = 'Seuil minimum'
                status_tone = 'warning'
            watch_candidates.append({
                'id': template.id,
                'product': template.display_name,
                'rayon': template.categ_id.display_name or '-',
                'status': status,
                'status_tone': status_tone,
                'stock': stock_qty,
                'rotation': sold_qty,
                'action': open_model('Produit — ' + template.display_name, 'product.template', [('id', '=', template.id)]),
            })
        max_watch_rotation = max((row['rotation'] for row in watch_candidates), default=0.0)
        for row in watch_candidates:
            if max_watch_rotation and row['rotation'] >= max_watch_rotation * 0.66:
                row['rotation_tone'] = 'high'
            elif max_watch_rotation and row['rotation'] >= max_watch_rotation * 0.33:
                row['rotation_tone'] = 'medium'
            else:
                row['rotation_tone'] = 'normal'
        watch_rows = watch_candidates[:30]

        alerts = [
            {'title': 'Rupture de stock', 'detail': f"{out_count} produits en rupture", 'time': '10:30', 'action': out_action, 'icon': 'fa fa-warning'},
            {'title': 'Stock minimum atteint', 'detail': f"{min_count} produits sous minimum", 'time': '10:15', 'action': min_action, 'icon': 'fa fa-level-down'},
            {'title': 'Demande d’approvisionnement', 'detail': f"{purchase_pending_count} demandes en attente", 'time': '09:45', 'action': procurement_items[0]['action'], 'icon': 'fa fa-clock-o'},
            {'title': 'Bon de transfert en attente', 'detail': f"{transfer_pending_count} bons à suivre", 'time': '09:30', 'action': actions['transfers'], 'icon': 'fa fa-exchange'},
            {'title': 'Paiement en attente', 'detail': f"{supplier_unpaid_count} factures fournisseurs à payer", 'time': '09:10', 'action': supplier_bills_action, 'icon': 'fa fa-money'},
            {'title': 'Factures clients impayées', 'detail': f"{billing['unpaid_count']} factures à relancer", 'time': '08:55', 'action': billing['unpaid_action'], 'icon': 'fa fa-file-text-o'},
            {'title': 'Surstock à optimiser', 'detail': f"{over_count} produits au-dessus du seuil", 'time': '08:45', 'action': over_action, 'icon': 'fa fa-cubes'},
        ]

        def fmt_datetime(value):
            if not value:
                return '—'
            return fields.Datetime.to_string(value)[:19].replace('-', '/')

        history_source_limit = 34
        activity_candidates = []
        for order in self.env['purchase.order'].search([], order='write_date desc', limit=history_source_limit):
            activity_candidates.append({
                'key': f'purchase.order-{order.id}',
                'sort_date': order.write_date or order.create_date,
                'date': fmt_datetime(order.write_date or order.create_date),
                'user': order.user_id.name or order.create_uid.name,
                'action': 'Bon de commande',
                'doc': order.name,
                'state': dict(order._fields['state'].selection).get(order.state, order.state),
                'action_ref': open_model('Bon de commande', 'purchase.order', [('id', '=', order.id)]),
            })
        for picking in self.env['stock.picking'].search([], order='write_date desc', limit=history_source_limit):
            activity_candidates.append({
                'key': f'stock.picking-{picking.id}',
                'sort_date': picking.write_date or picking.create_date,
                'date': fmt_datetime(picking.write_date or picking.create_date),
                'user': picking.user_id.name or picking.create_uid.name,
                'action': 'Mouvement de stock',
                'doc': picking.name,
                'state': dict(picking._fields['state'].selection).get(picking.state, picking.state),
                'action_ref': open_model('Mouvement de stock', 'stock.picking', [('id', '=', picking.id)]),
            })
        for payment in self.env['account.payment'].search([], order='write_date desc', limit=history_source_limit):
            activity_candidates.append({
                'key': f'account.payment-{payment.id}',
                'sort_date': payment.write_date or payment.create_date,
                'date': fmt_datetime(payment.write_date or payment.create_date),
                'user': payment.create_uid.name,
                'action': 'Paiement',
                'doc': payment.name or payment.display_name,
                'state': dict(payment._fields['state'].selection).get(payment.state, payment.state),
                'action_ref': open_model('Paiement', 'account.payment', [('id', '=', payment.id)]),
            })
        activities = sorted(activity_candidates, key=lambda item: item['sort_date'] or fields.Datetime.now(), reverse=True)

        audit = []
        if 'ir.logging' in self.env.registry:
            for log in self.env['ir.logging'].sudo().search([], order='create_date desc', limit=history_source_limit):
                audit.append({
                    'key': f'ir.logging-{log.id}',
                    'sort_date': log.create_date,
                    'date': fmt_datetime(log.create_date),
                    'user': log.create_uid.name,
                    'action': (log.message or log.name or log.type or '-')[:80],
                    'module': log.name or log.type or '-',
                })
        if not audit and 'mail.message' in self.env.registry:
            for message in self.env['mail.message'].search([], order='date desc', limit=history_source_limit):
                audit.append({
                    'key': f'mail.message-{message.id}',
                    'sort_date': message.date,
                    'date': fmt_datetime(message.date),
                    'user': message.author_id.name or message.create_uid.name,
                    'action': (message.subject or message.record_name or message.message_type or '-')[:80],
                    'module': message.model or '-',
                })

        history_items = []
        audit_events = self.env['primetech.audit.event'].sudo().search([], order='event_date desc, id desc', limit=100)
        if audit_events:
            event_type_labels = dict(self.env['primetech.audit.event']._fields['event_type'].selection)
            event_styles = {
                'create': ('fa-plus-circle', 'success', 'Créé'),
                'write': ('fa-pencil', 'warning', 'Modifié'),
                'unlink': ('fa-times-circle', 'danger', 'Supprimé'),
                'print': ('fa-print', 'info', 'Imprimé'),
                'event': ('fa-bolt', 'purple', 'Événement'),
            }
            for event in audit_events:
                icon, tone, status = event_styles.get(event.event_type, ('fa-circle', 'info', event_type_labels.get(event.event_type, event.event_type)))
                event_action = open_model(
                    event.document_name or event.model_label,
                    event.model_name,
                    [('id', '=', event.res_id)],
                ) if event.res_id and event.model_name in self.env.registry else False
                history_items.append({
                    'key': f'audit-event-{event.id}',
                    'sort_date': event.event_date,
                    'date': fmt_datetime(event.event_date),
                    'source': _('Audit'),
                    'user': event.user_id.name,
                    'role': event.user_role or 'Utilisateur',
                    'action': event.action_label,
                    'description': event.details or event.action_label,
                    'doc': event.document_name or '-',
                    'state': status,
                    'tone': tone,
                    'icon': icon,
                    'action_ref': event_action,
                })
        if len(history_items) < 100:
            for item in activity_candidates:
                history_items.append({
                    'key': item['key'],
                    'sort_date': item['sort_date'],
                    'date': item['date'],
                    'source': _('Activité'),
                    'user': item['user'],
                    'role': _('Utilisateur'),
                    'action': item['action'],
                    'description': item['state'],
                    'doc': item['doc'],
                    'state': item['state'],
                    'tone': 'info',
                    'icon': 'fa-bolt',
                    'action_ref': item['action_ref'],
                })
            for item in audit:
                history_items.append({
                    'key': item['key'],
                    'sort_date': item.get('sort_date'),
                    'date': item['date'],
                    'source': _('Journal'),
                    'user': item['user'],
                    'role': _('Système'),
                    'action': item['action'],
                    'description': item['module'],
                    'doc': '-',
                    'state': _('Journal'),
                    'tone': 'purple',
                    'icon': 'fa-shield',
                    'action_ref': False,
                })
        history_items = sorted(
            history_items,
            key=lambda item: item.get('sort_date') or fields.Datetime.now(),
            reverse=True,
        )[:100]

        perf_start = fields.Datetime.to_datetime(start)
        perf_end = fields.Datetime.to_datetime(end) + timedelta(days=1)
        perf_done_domain = [('state', '=', 'done'), ('date_done', '>=', perf_start), ('date_done', '<', perf_end)]
        perf_recent_domain = [('create_date', '>=', perf_start), ('create_date', '<', perf_end), ('state', '!=', 'cancel')]
        perf_cancelled_domain = [('create_date', '>=', perf_start), ('create_date', '<', perf_end), ('state', '=', 'cancel')]
        perf_done_pickings = StockPicking.search(perf_done_domain)
        perf_recent_pickings = StockPicking.search(perf_recent_domain)
        perf_cancelled = StockPicking.search_count(perf_cancelled_domain)
        delay_hours = [
            (picking.date_done - picking.scheduled_date).total_seconds() / 3600.0
            for picking in perf_done_pickings
            if picking.date_done and picking.scheduled_date
        ]
        service_rate = round(len(perf_done_pickings) / len(perf_recent_pickings) * 100, 1) if perf_recent_pickings else 0
        rupture_rate = round(out_count / template_count * 100, 2) if template_count else 0
        delivery_delay = round(sum(delay_hours) / len(delay_hours), 1) if delay_hours else 0
        error_rate = round(perf_cancelled / (len(perf_recent_pickings) + perf_cancelled) * 100, 2) if (perf_recent_pickings or perf_cancelled) else 0

        def high_is_good_status(value, success_limit, warning_limit):
            if value >= success_limit:
                return 'success', _('Objectif atteint')
            if value >= warning_limit:
                return 'warning', _('À suivre')
            return 'danger', _('Action requise')

        def low_is_good_status(value, success_limit, warning_limit):
            if value <= success_limit:
                return 'success', _('Sous contrôle')
            if value <= warning_limit:
                return 'warning', _('À suivre')
            return 'danger', _('Action requise')

        service_tone, service_indicator = (
            high_is_good_status(service_rate, 95, 85)
            if perf_recent_pickings else ('muted', _('Aucune opération sur la période'))
        )
        rupture_tone, rupture_indicator = low_is_good_status(rupture_rate, 2, 8)
        delay_tone, delay_indicator = (
            low_is_good_status(delivery_delay, 24, 48)
            if delay_hours else ('muted', _('Aucune livraison terminée'))
        )
        error_tone, error_indicator = (
            low_is_good_status(error_rate, 1, 3)
            if (perf_recent_pickings or perf_cancelled) else ('muted', _('Aucune préparation sur la période'))
        )
        performance = [
            {'label': 'Taux de service', 'value': f'{service_rate}%', 'trend': period_label, 'tone': service_tone, 'indicator': service_indicator, 'icon': 'fa-check-circle', 'percent': min(max(service_rate, 0), 100), 'action': open_model(_('Analyse du taux de service'), 'stock.picking', perf_recent_domain)},
            {'label': 'Taux de rupture', 'value': f'{rupture_rate}%', 'trend': f'{out_count} produits', 'tone': rupture_tone, 'indicator': rupture_indicator, 'icon': 'fa-exclamation-triangle', 'percent': min(max(rupture_rate, 0), 100), 'action': out_action},
            {'label': 'Délai moyen livraison', 'value': f'{delivery_delay} h', 'trend': period_label, 'tone': delay_tone, 'indicator': delay_indicator, 'icon': 'fa-clock-o', 'percent': min(max(delivery_delay / 24 * 100, 0), 100), 'action': open_model(_('Analyse des délais de livraison'), 'stock.picking', perf_done_domain)},
            {'label': 'Taux d’erreur préparation', 'value': f'{error_rate}%', 'trend': f'{perf_cancelled} annulés', 'tone': error_tone, 'indicator': error_indicator, 'icon': 'fa-bug', 'percent': min(max(error_rate, 0), 100), 'action': open_model(_('Préparations annulées'), 'stock.picking', perf_cancelled_domain)},
        ]
        history_action = open_model(
            _('Historique complet : actions, événements et audit'),
            'primetech.audit.event',
            [],
            {'search_default_group_day': 0, 'primetech_history_full': True},
        )
        activity_history_action = history_action
        audit_history_action = history_action
        # Store sales are aggregated separately, but this operational card
        # still needs the warehouses to calculate picking workloads.
        warehouses = self.env['stock.warehouse'].search([])
        warehouse_load = []
        max_load_units = 0
        for warehouse in warehouses:
            prep_count = StockPicking.search_count([('picking_type_id.warehouse_id', '=', warehouse.id), ('state', '=', 'assigned')])
            order_count = StockPicking.search_count([('picking_type_id.warehouse_id', '=', warehouse.id), ('state', 'in', ['confirmed', 'waiting'])])
            max_load_units = max(max_load_units, prep_count + order_count)
            warehouse_load.append({
                'name': warehouse.display_name,
                'prep': prep_count,
                'orders': order_count,
                'load_units': prep_count + order_count,
                'action': open_model('Charge ' + warehouse.display_name, 'stock.picking', [('picking_type_id.warehouse_id', '=', warehouse.id), ('state', 'not in', ['done', 'cancel'])]),
            })
        for line in warehouse_load:
            line['load'] = (line['load_units'] / max_load_units * 100 if max_load_units else 0)
            if not line['load_units']:
                line.update({'load_tone': 'muted', 'load_indicator': _('Sans activité')})
            elif line['load'] >= 80:
                line.update({'load_tone': 'primary', 'load_indicator': _('Prioritaire')})
            elif line['load'] >= 45:
                line.update({'load_tone': 'warning', 'load_indicator': _('À suivre')})
            else:
                line.update({'load_tone': 'info', 'load_indicator': _('Actif')})
        warehouse_load = sorted(warehouse_load, key=lambda line: line['load_units'], reverse=True)[:8]

        def stock_alert(label, value, active_tone, action, icon):
            return {
                'label': label,
                'value': value,
                'tone': active_tone if value else 'success',
                'indicator': _('Action requise') if value else _('Sous contrôle'),
                'icon': icon,
                'action': action,
            }

        logistics_alerts = [
            stock_alert(_('Rupture de stock'), out_count, 'danger', out_action, 'fa-times-circle'),
            stock_alert(_('Stock minimum atteint'), min_count, 'warning', min_action, 'fa-exclamation-triangle'),
            stock_alert(_('Surstock'), over_count, 'info', over_action, 'fa-cubes'),
            stock_alert(_('Stock proche péremption'), len(expiry_template_ids), 'warning', expiry_action, 'fa-clock-o'),
            stock_alert(_('Articles à faible rotation'), len(slow_template_ids), 'info', slow_action, 'fa-line-chart'),
        ]
        gross_margin_value = overview['revenue_total'] - overview.get('purchase_cost', 0.0)
        period_day_count = max((end - start).days + 1, 1)
        daily_result = gross_margin_value / period_day_count
        return {
            'kpis': [
                {'label': "Chiffre d'affaires", 'value': overview['revenue_total'], 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-line-chart', 'tone': 'blue', 'action': actions['sales']},
                {'label': 'Marge brute', 'value': gross_margin_value, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-pie-chart', 'tone': 'green', 'action': actions['sales']},
                {'label': 'Résultat journalier', 'value': daily_result, 'suffix': 'FCFA', 'trend': f'Moyenne sur {period_day_count} jour(s)', 'icon': 'fa fa-cog', 'tone': 'purple', 'action': actions['finance']},
                {'label': 'Total factures', 'value': global_invoice_total, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-file-text-o', 'tone': 'orange', 'action': open_model('Factures clients — ' + period_label, 'account.move', global_invoice_domain, {'search_default_posted': 1})},
                {'label': 'Créances clients', 'value': global_receivable_total, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-money', 'tone': 'red', 'action': open_model('Créances clients — ' + period_label, 'account.move', global_invoice_domain + [('amount_residual', '>', 0)], {'search_default_posted': 1})},
                {'label': 'Achats fournisseurs', 'value': purchase_total_confirmed, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-shopping-cart', 'tone': 'cyan', 'action': actions['purchase']},
                {'label': 'Factures fournisseurs', 'value': supplier_bill_total, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-file-text', 'tone': 'indigo', 'action': supplier_bills_action},
                {'label': 'Dettes fournisseurs', 'value': supplier_debt_total, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-credit-card', 'tone': 'teal', 'action': supplier_bills_action},
                {'label': 'Paiements fournisseurs', 'value': supplier_payment_total, 'suffix': 'FCFA', 'trend': period_label, 'icon': 'fa fa-bank', 'tone': 'yellow', 'action': supplier_payments_action},
                {'label': 'Fournisseurs actifs', 'value': len(active_supplier_ids), 'suffix': '', 'trend': period_label, 'icon': 'fa fa-users', 'tone': 'green', 'action': supplier_action},
            ],
            'stores': stores,
            'store_summary': store_summary,
            'partner_balance_kpis': receivable_kpis,
            'cashflow_analysis': cashflow_analysis,
            'store_period': store_period,
            'store_period_label': store_label,
            'revenue_chart': revenue_chart,
            'revenue_period': revenue_period,
            'period_label': period_label,
            'performance_period_label': period_label,
            'cash': cash_lines,
            'banks': banks,
            'billing': billing,
            'categories': categories_payload,
            'current_user': {'name': self.env.user.name, 'status': 'En ligne'},
            'stock': {
                'value': stock_value,
                'scope': stock_scope,
                'products': template_count,
                'ruptures': out_count,
                'minimum': min_count,
                'overstock': over_count,
                'actions': {'products': product_action, 'ruptures': out_action, 'minimum': min_action, 'overstock': over_action},
            },
            'alerts': alerts,
            'settings': settings,
            'quick_actions': [
                {'label': "Créer une demande d’approvisionnement", 'icon': 'fa fa-cart-plus', 'action': actions['purchase']},
                {'label': 'Créer un bon de transfert', 'icon': 'fa fa-truck', 'action': actions['transfers']},
                {'label': 'Nouveau devis client', 'icon': 'fa fa-file-text-o', 'action': open_model('Nouveau devis client', 'account.move', [('move_type', '=', 'out_invoice')])},
                {'label': 'Nouveau bon de commande', 'icon': 'fa fa-shopping-cart', 'action': actions['purchase']},
                {'label': 'Nouveau produit', 'icon': 'fa fa-cube', 'action': actions['products']},
                {'label': 'Rapport de vente', 'icon': 'fa fa-bar-chart', 'action': actions['sales']},
            ],
            'supply': {
                'requests': supply_requests,
                'transfers': supply_transfers,
                'customers': supply_customers,
            },
            'warehouse_load': warehouse_load,
            'logistics_alerts': logistics_alerts,
            'vehicles': vehicles,
            'drivers': [{'driver': e.name, 'vehicle': '-', 'status': 'Disponible' if e.active else 'Inactif', 'next': '—', 'action': open_model('Chauffeur', 'hr.employee', [('id', '=', e.id)])} for e in (self.env['hr.employee'].search(['|', ('job_id.name', 'ilike', 'chauffeur'), ('job_title', 'ilike', 'chauffeur')], limit=10) if 'hr.employee' in self.env.registry else [])],
            'top_watch': watch_rows,
            'audit': audit,
            'activities': activities,
            'history_items': history_items,
            'performance': performance,
            'activity_history_action': activity_history_action,
            'audit_history_action': audit_history_action,
        }

    @api.model
    def get_executive_kpi(self, kpi_key, filters=None):
        """Return only the payload needed by one filtered executive KPI.

        Individual card filters used to trigger the complete executive board,
        including logistics, audit history and every unrelated accounting
        calculation.  Keeping the response scoped makes the dashboard remain
        responsive on larger databases.
        """
        filters = dict(filters or {})
        handlers = {
            'cash_period': self._get_cash_kpi_payload,
            'billing_period': self._get_billing_kpi_payload,
            'stock_scope': self._get_stock_kpi_payload,
            'store_period': self._get_store_kpi_payload,
            'revenue_period': self._get_revenue_kpi_payload,
            'cashflow_period': self._get_cashflow_kpi_payload,
            'top_watch_period': self._get_top_watch_kpi_payload,
            'customer_receivable_filter': self._get_partner_kpi_payload,
            'supplier_receivable_filter': self._get_partner_kpi_payload,
        }
        handler = handlers.get(kpi_key)
        return handler(filters) if handler else {}

    def _get_cash_kpi_payload(self, filters):
        period_filters = self._scoped_period_filters(filters, 'cash_period', filters.get('period', 'today'))
        cash_lines = self._get_pos_session_state(period_filters).get('sessions', [])
        pos_action = self._dashboard_open_model('Sessions de caisse', 'pos.session', []) if 'pos.session' in self.env.registry else self._dashboard_open_model('Ventes PDV', 'pos.order', [])
        if not cash_lines:
            cash_lines = [{'name': 'Aucune caisse', 'state': '-', 'user': '-', 'cashier': '-', 'opening_date': '-', 'balance': 0, 'current_balance': 0, 'closing_balance': 0, 'orders_total': 0, 'status_class': 'muted', 'action': pos_action}]
        else:
            for line in cash_lines:
                line['action'] = self._dashboard_open_model('Session de caisse', 'pos.session', [('id', '=', line['id'])])
        return {'cash': cash_lines}

    def _get_billing_kpi_payload(self, filters):
        billing_period = self._period_filter_value(filters, 'billing_period', filters.get('period', 'month'))
        billing_filters = self._scoped_period_filters(filters, 'billing_period', filters.get('period', 'month'))
        invoice_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')] + self._get_date_domain(billing_filters, 'invoice_date')
        totals = self.env['account.move'].read_group(invoice_domain, ['amount_total:sum', 'amount_residual:sum'], [])
        totals = totals[0] if totals else {}
        billing_total = totals.get('amount_total', 0.0) or 0.0
        billing_balance = totals.get('amount_residual', 0.0) or 0.0
        unpaid_domain = invoice_domain + [('payment_state', 'in', ['not_paid', 'partial'])]
        return {
            'billing': {
                'period': billing_period,
                'total': billing_total,
                'paid': billing_total - billing_balance,
                'balance': billing_balance,
                'count': self.env['account.move'].search_count(invoice_domain),
                'unpaid_count': self.env['account.move'].search_count(unpaid_domain),
                'unpaid_rate': billing_balance / billing_total * 100 if billing_total else 0.0,
                'action': self._dashboard_open_model('Factures clients', 'account.move', invoice_domain, {'search_default_posted': 1}),
                'payments_action': self._dashboard_open_model('Factures clients encaissées', 'account.move', invoice_domain + [('payment_state', 'in', ['paid', 'in_payment'])], {'search_default_posted': 1}),
                'unpaid_action': self._dashboard_open_model('Factures clients impayées', 'account.move', unpaid_domain, {'search_default_posted': 1}),
            },
        }

    def _get_stock_kpi_payload(self, filters):
        Product = self.env['product.product']
        ProductTemplate = self.env['product.template']
        Quant = self.env['stock.quant']
        stock_scope = self._period_filter_value(filters, 'stock_scope', 'all')
        template_domain = []
        if stock_scope == 'sale':
            template_domain.append(('sale_ok', '=', True))
        elif stock_scope == 'purchase':
            template_domain.append(('purchase_ok', '=', True))
        template_count = ProductTemplate.search_count(template_domain)
        product_domain = []
        if template_domain:
            template_ids = ProductTemplate.search(template_domain).ids
            if template_ids:
                product_domain = [('product_tmpl_id', 'in', template_ids)]
            else:
                template_domain = []
                template_count = ProductTemplate.search_count(template_domain)
        quant_domain = [('location_id.usage', '=', 'internal')] + ([('product_id', 'in', Product.search(product_domain).ids)] if product_domain else [])
        value_field = 'value' if 'value' in Quant._fields else 'inventory_value' if 'inventory_value' in Quant._fields else None
        groups = Quant.read_group(quant_domain, ['quantity'] + ([value_field] if value_field else []), ['product_id'], lazy=False)
        products = Product.browse([group['product_id'][0] for group in groups if group.get('product_id')])
        product_by_id = {product.id: product for product in products}
        quantities = defaultdict(float)
        values = defaultdict(float)
        for group in groups:
            product_data = group.get('product_id')
            product = product_by_id.get(product_data[0]) if product_data else False
            if not product:
                continue
            quantity = group.get('quantity', 0.0) or 0.0
            template = product.product_tmpl_id
            quantities[template.id] += quantity
            grouped_value = group.get(value_field, 0.0) if value_field else 0.0
            values[template.id] += grouped_value or quantity * (product.standard_price or template.standard_price or template.list_price or 0.0)
        settings = self.env['primetech.reporting.settings'].get_values()
        minimum = settings['stock_min_alert_threshold']
        overstock = settings['stock_overstock_threshold']
        positive_templates = {template_id for template_id, quantity in quantities.items() if quantity > 0}
        out_count = max(template_count - len(positive_templates), 0)
        min_count = sum(1 for quantity in quantities.values() if 0 < quantity <= minimum)
        over_count = sum(1 for quantity in quantities.values() if quantity >= overstock)
        return {
            'stock': {
                'value': sum(values.values()),
                'scope': stock_scope,
                'products': template_count,
                'ruptures': out_count,
                'minimum': min_count,
                'overstock': over_count,
                'actions': {
                    'products': self._dashboard_open_model('Produits stockables', 'product.template', template_domain),
                    'ruptures': self._dashboard_open_model('Produits en rupture', 'product.template', template_domain + [('qty_available', '<=', 0)]),
                    'minimum': self._dashboard_open_model('Produits sous stock minimum', 'product.template', template_domain + [('qty_available', '>', 0), ('qty_available', '<=', minimum)]),
                    'overstock': self._dashboard_open_model('Produits en surstock', 'product.template', template_domain + [('qty_available', '>=', overstock)]),
                },
            },
        }

    def _get_store_kpi_payload(self, filters):
        period = self._period_filter_value(filters, 'store_period', filters.get('period', 'month'))
        period_filters = self._scoped_period_filters(filters, 'store_period', filters.get('period', 'month'))
        start, end = self._get_period_bounds(period_filters)
        sale_domain = [('state', 'in', ['sale', 'done']), ('date_order', '>=', start), ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1))]
        warehouse_values = defaultdict(float)
        warehouse_sale_orders = defaultdict(int)
        warehouse_pos_orders = defaultdict(int)
        warehouse_pos_configs = defaultdict(set)
        for group in self.env['sale.order'].read_group(sale_domain, ['amount_total:sum'], ['warehouse_id'], lazy=False):
            warehouse_data = group.get('warehouse_id')
            if warehouse_data:
                warehouse_id = warehouse_data[0]
                warehouse_values[warehouse_id] += group.get('amount_total', 0.0) or 0.0
                warehouse_sale_orders[warehouse_id] += group.get('__count', 0) or 0
        pos_domain = [
            ('date_order', '>=', start),
            ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
            ('state', 'not in', ['draft', 'cancel']),
        ]
        if 'pos.order' in self.env.registry:
            pos_groups = self.env['pos.order'].read_group(pos_domain, ['amount_total:sum'], ['config_id'], lazy=False)
            configs = self.env['pos.config'].browse([group['config_id'][0] for group in pos_groups if group.get('config_id')])
            config_by_id = {config.id: config for config in configs}
            for group in pos_groups:
                config_data = group.get('config_id')
                config = config_by_id.get(config_data[0]) if config_data else False
                warehouse = config.picking_type_id.warehouse_id if config and config.picking_type_id else False
                if warehouse:
                    warehouse_values[warehouse.id] += group.get('amount_total', 0.0) or 0.0
                    warehouse_pos_orders[warehouse.id] += group.get('__count', 0) or 0
                    warehouse_pos_configs[warehouse.id].add(config.id)
        maximum = max(warehouse_values.values(), default=0.0)
        total = sum(warehouse_values.values())
        tones = ['green', 'orange', 'blue', 'purple', 'cyan', 'pink', 'slate']
        warehouses = self.env['stock.warehouse'].search([])
        stores = []
        sorted_warehouses = sorted(
            warehouses,
            key=lambda item: (warehouse_values.get(item.id, 0.0), item.display_name),
            reverse=True,
        )
        for index, warehouse in enumerate(sorted_warehouses):
            value = warehouse_values.get(warehouse.id, 0.0)
            sale_orders = warehouse_sale_orders.get(warehouse.id, 0)
            pos_orders = warehouse_pos_orders.get(warehouse.id, 0)
            order_count = sale_orders + pos_orders
            if sale_orders:
                action = self._dashboard_open_model(
                    'Ventes ' + warehouse.display_name,
                    'sale.order',
                    sale_domain + [('warehouse_id', '=', warehouse.id)],
                )
            elif pos_orders:
                action = self._dashboard_open_model(
                    'Ventes PDV ' + warehouse.display_name,
                    'pos.order',
                    pos_domain + [('config_id', 'in', list(warehouse_pos_configs[warehouse.id]))],
                )
            else:
                action = self._dashboard_open_model(
                    'Magasin ' + warehouse.display_name,
                    'stock.warehouse',
                    [('id', '=', warehouse.id)],
                )
            stores.append({
                'id': warehouse.id,
                'name': warehouse.display_name,
                'code': warehouse.code or '',
                'rank': index + 1,
                'value': value,
                'percent': value / maximum * 100 if maximum else 0.0,
                'share': value / total * 100 if total else 0.0,
                'orders': order_count,
                'sale_orders': sale_orders,
                'pos_orders': pos_orders,
                'average_ticket': value / order_count if order_count else 0.0,
                'tone': tones[index % len(tones)],
                'action': action,
            })
        labels = {'today': "Aujourd'hui", 'week': 'Cette semaine', 'month': 'Ce mois', 'quarter': 'Ce trimestre', 'year': 'Cette année', 'custom': 'Période sélectionnée'}
        total_orders = sum(store['orders'] for store in stores)
        return {
            'stores': stores,
            'store_summary': {
                'total': total,
                'orders': total_orders,
                'average_ticket': total / total_orders if total_orders else 0.0,
                'active_stores': sum(1 for store in stores if store['orders'] or store['value']),
                'store_count': len(stores),
            },
            'store_period': period,
            'store_period_label': labels.get(period, labels['month']),
        }

    def _get_revenue_kpi_payload(self, filters):
        period = self._period_filter_value(filters, 'revenue_period', filters.get('period', 'month'))
        period_filters = self._scoped_period_filters(filters, 'revenue_period', filters.get('period', 'month'))
        start, end = self._get_period_bounds(period_filters)
        chart_group = 'month' if period == 'year' or (end - start).days > 90 else 'day'
        keys = []
        current = start.replace(day=1) if chart_group == 'month' else start
        while current <= end:
            keys.append(current)
            current = current + relativedelta(months=1) if chart_group == 'month' else current + timedelta(days=1)
        values = {key: {'sale': 0.0, 'pos': 0.0} for key in keys}

        def bucket(record_date):
            record_date = fields.Datetime.to_datetime(record_date)
            day = record_date.date()
            return day.replace(day=1) if chart_group == 'month' else day

        sale_domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', fields.Datetime.to_datetime(start)),
            ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
        ]
        for order in self.env['sale.order'].search(sale_domain):
            key = bucket(order.date_order)
            if key in values:
                values[key]['sale'] += order.amount_total or 0.0

        pos_domain = [
            ('state', 'not in', ['draft', 'cancel']),
            ('date_order', '>=', fields.Datetime.to_datetime(start)),
            ('date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)),
        ]
        if 'pos.order' in self.env.registry:
            for order in self.env['pos.order'].search(pos_domain):
                key = bucket(order.date_order)
                if key in values:
                    values[key]['pos'] += order.amount_total or 0.0
        maximum = max((item['sale'] + item['pos'] for item in values.values()), default=0.0)
        labels = {'today': "Aujourd'hui", 'week': 'Cette semaine', 'month': 'Ce mois', 'quarter': 'Ce trimestre', 'year': 'Cette année', 'custom': 'Période sélectionnée'}
        return {
            'revenue_period': period,
            'revenue_chart': {
                'subtitle': _('Ventes commerciales et points de vente — %s') % labels.get(period, labels['month']),
                'items': [{
                    'key': key.isoformat(),
                    'label': key.strftime('%m/%Y') if chart_group == 'month' else key.strftime('%d/%m'),
                    'income': values[key]['sale'],
                    'expense': values[key]['pos'],
                    'value': values[key]['sale'] + values[key]['pos'],
                    'height': (values[key]['sale'] + values[key]['pos']) / maximum * 100 if maximum else 0.0,
                } for key in keys],
            },
            'categories': self._get_revenue_categories_payload(period_filters, self._dashboard_open_model),
        }

    def _get_revenue_categories_payload(self, period_filters, open_model):
        """Build category sales for the exact period selected on the revenue KPI."""
        Product = self.env['product.product']
        category_revenue = defaultdict(float)
        category_ids = {}

        def add_grouped_revenue(model, domain, amount_field):
            groups = self.env[model].read_group(domain, [amount_field], ['product_id'], lazy=False)
            products = Product.browse([group['product_id'][0] for group in groups if group.get('product_id')])
            product_by_id = {product.id: product for product in products}
            for group in groups:
                product_data = group.get('product_id')
                product = product_by_id.get(product_data[0]) if product_data else False
                if not product:
                    continue
                category = product.categ_id
                category_name = category.display_name or 'Sans catégorie'
                category_revenue[category_name] += group.get(amount_field, 0.0) or 0.0
                category_ids[category_name] = category.id

        sale_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('product_id', '!=', False),
        ] + self._get_date_domain(period_filters, 'order_id.date_order')
        add_grouped_revenue('sale.order.line', sale_domain, 'price_total')
        if 'pos.order.line' in self.env.registry:
            pos_domain = [('order_id.state', 'not in', ['draft', 'cancel']), ('product_id', '!=', False)] + self._get_date_domain(period_filters, 'order_id.date_order')
            add_grouped_revenue('pos.order.line', pos_domain, 'price_subtotal_incl')
        total = sum(category_revenue.values())
        return {
            'total': total,
            'items': [{
                'name': name,
                'value': value,
                'percent': value / total * 100 if total else 0.0,
                'action': open_model('Produits catégorie ' + name, 'product.product', [('categ_id', 'child_of', category_ids[name])] if category_ids.get(name) else []),
            } for name, value in sorted(category_revenue.items(), key=lambda item: item[1], reverse=True)[:5]],
            'action': open_model('Analyse détaillée des ventes par catégorie', 'sale.order.line', sale_domain, {'group_by': ['product_id']}, 'pivot,graph,list'),
            'products_action': open_model('Catalogue des produits par catégorie', 'product.product', [('categ_id', '!=', False)], {'group_by': ['categ_id']}, 'list,kanban'),
        }

    def _get_cashflow_kpi_payload(self, filters):
        return {'cashflow_analysis': self._get_cashflow_analysis(self._dashboard_open_model, filters)}

    def _get_partner_kpi_payload(self, filters):
        return {'partner_balance_kpis': self._get_partner_balance_kpis(self._dashboard_open_model, filters)}

    def _get_top_watch_kpi_payload(self, filters):
        Product = self.env['product.product']
        ProductTemplate = self.env['product.template']
        period_filters = self._scoped_period_filters(filters, 'top_watch_period', filters.get('period', 'month'))
        start, end = self._get_period_bounds(period_filters)
        order_domain = [('order_id.date_order', '>=', fields.Datetime.to_datetime(start)), ('order_id.date_order', '<', fields.Datetime.to_datetime(end) + timedelta(days=1)), ('product_id', '!=', False)]
        quantities = defaultdict(float)

        def add_groups(model, domain, field):
            groups = self.env[model].read_group(domain, [field], ['product_id'], lazy=False)
            products = Product.browse([group['product_id'][0] for group in groups if group.get('product_id')])
            product_by_id = {product.id: product for product in products}
            for group in groups:
                product_data = group.get('product_id')
                product = product_by_id.get(product_data[0]) if product_data else False
                if product:
                    quantities[product.product_tmpl_id.id] += group.get(field, 0.0) or 0.0

        if 'sale.order.line' in self.env.registry:
            add_groups('sale.order.line', [('order_id.state', 'in', ['sale', 'done'])] + order_domain, 'product_uom_qty')
        add_groups('account.move.line', [('move_id.move_type', '=', 'out_invoice'), ('move_id.state', '=', 'posted'), ('move_id.invoice_date', '>=', start), ('move_id.invoice_date', '<=', end), ('product_id', '!=', False)], 'quantity')
        if 'pos.order.line' in self.env.registry:
            add_groups('pos.order.line', order_domain, 'qty')

        minimum = self.env['primetech.reporting.settings'].get_values()['stock_min_alert_threshold']
        templates = {template.id: template for template in ProductTemplate.browse(list(quantities))}
        rows = []
        for template_id, rotation in sorted(quantities.items(), key=lambda item: item[1], reverse=True):
            template = templates.get(template_id)
            if not template:
                continue
            stock = template.qty_available
            if rotation <= 0 or stock > minimum:
                continue
            status, tone = ('Rupture', 'danger') if stock <= 0 else ('Stock critique', 'critical') if stock <= minimum * .5 else ('Seuil minimum', 'warning')
            rows.append({
                'id': template.id,
                'product': template.display_name,
                'rayon': template.categ_id.display_name or '-',
                'status': status,
                'status_tone': tone,
                'stock': stock,
                'rotation': rotation,
                'action': self._dashboard_open_model('Produit — ' + template.display_name, 'product.template', [('id', '=', template.id)]),
            })
        maximum = max((row['rotation'] for row in rows), default=0.0)
        for row in rows:
            row['rotation_tone'] = 'high' if maximum and row['rotation'] >= maximum * .66 else 'medium' if maximum and row['rotation'] >= maximum * .33 else 'normal'
        return {'top_watch': rows[:30]}

    def _get_partner_balance_kpis(self, open_model, filters=None):
        """Build customer and supplier balances directly from account.move.line.

        Receivable and payable accounts are deliberately aggregated separately so
        a partner can appear in both lists, including with a zero balance. The row
        amount and drill-down action share the exact same ledger domain.
        """
        filters = filters or {}
        kpi_filters = filters.get('kpi_filters', {}) or {}
        AccountMoveLine = self.env['account.move.line']
        base_domain = [
            ('partner_id', '!=', False),
            ('parent_state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        account_types = ('asset_receivable', 'liability_payable')
        grouped_by_type = {}
        partner_labels = {}
        for account_type in account_types:
            groups = AccountMoveLine.read_group(
                base_domain + [('account_id.account_type', '=', account_type)],
                ['debit:sum', 'credit:sum', 'balance:sum'],
                ['partner_id'],
                lazy=False,
            )
            grouped_by_type[account_type] = {}
            for group in groups:
                partner_data = group.get('partner_id')
                if not partner_data:
                    continue
                partner_id, partner_label = partner_data
                partner_labels[partner_id] = partner_label
                grouped_by_type[account_type][partner_id] = group

        def filtered_rows(rows, filter_key, payment_field):
            if filter_key == 'high':
                magnitudes = [abs(row['balance']) for row in rows]
                average = sum(magnitudes) / len(magnitudes) if magnitudes else 0.0
                threshold = max(sum(magnitudes) * 0.10, average)
                return [row for row in rows if abs(row['balance']) >= threshold]
            if filter_key == 'with_debit':
                return [row for row in rows if row['debit'] > 0]
            if filter_key == 'with_credit':
                return [row for row in rows if row['credit'] > 0]
            if filter_key == 'without_payment':
                return [row for row in rows if row[payment_field] <= 0]
            return rows

        def build_kpi(title, account_type, filter_key, payment_field, reverse):
            ledger_domain = base_domain + [('account_id.account_type', '=', account_type)]
            rows = []
            account_groups = grouped_by_type[account_type]
            for partner_id, partner_label in partner_labels.items():
                group = account_groups.get(partner_id, {})
                balance = group.get('balance') or 0.0
                debit = group.get('debit') or 0.0
                credit = group.get('credit') or 0.0
                if not debit and not credit and not balance:
                    continue
                partner_domain = ledger_domain + [('partner_id', '=', partner_id)]
                abs_balance = abs(balance)
                if abs_balance <= 0.01:
                    status = 'soldé'
                    status_class = 'ok'
                elif debit and credit:
                    status = 'partiel'
                    status_class = 'warn'
                else:
                    status = 'non réglé'
                    status_class = 'danger'
                rows.append({
                    'partner_id': partner_id,
                    'partner': partner_label,
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'status': status,
                    'status_class': status_class,
                    'action': open_model(
                        f"{title} - {partner_label}",
                        'account.move.line',
                        partner_domain,
                        {'group_by': ['partner_id']},
                        'list,pivot,graph',
                    ),
                })
            rows = [row for row in rows if abs(row['balance']) > 0.01]
            rows.sort(key=lambda row: abs(row['balance']), reverse=True)
            filtered = filtered_rows(rows, filter_key, payment_field)
            return {
                'title': title,
                'total': sum(row['balance'] for row in rows),
                'count': len(rows),
                'filtered_count': len(filtered),
                'default_filtered_count': len(filtered),
                'filter': filter_key or 'all',
                # The card now keeps the complete result set locally. Its
                # compact scroll area controls visual density while search,
                # preview and print all use the exact visible list.
                'rows': filtered,
                'default_rows': filtered,
                'all_rows': rows,
                'action': open_model(
                    f"Liste exhaustive - {title}",
                    'account.move.line',
                    ledger_domain,
                    {'group_by': ['partner_id']},
                    'list,pivot,graph',
                ),
            }

        # Both KPI payloads are always built for the executive board. Do not
        # condition this return on the removed search_type/requested_types RPC
        # flow: live searching now happens locally against each all_rows list.
        customers = build_kpi(
            'Top créances client',
            'asset_receivable',
            kpi_filters.get('customer_receivable_filter', 'all'),
            'credit',
            True,
        )
        suppliers = build_kpi(
            'Top créances fournisseur',
            'liability_payable',
            kpi_filters.get('supplier_receivable_filter', 'all'),
            'debit',
            False,
        )
        return {'customers': customers, 'suppliers': suppliers}

    @api.model
    def get_dashboard_kpis(self, filters=None):
        filters = filters or {}
        today = date.today()
        current_month_start = today.replace(day=1)
        previous_month_start = current_month_start - relativedelta(months=1)
        sales = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]).mapped('amount_untaxed'))
        purchases = sum(self.env['purchase.order'].search([('state', 'in', ['purchase', 'done'])]).mapped('amount_untaxed'))
        gross_margin = sales - purchases
        cash_balance = sum(self.env['account.account'].search([('account_type', '=', 'asset_cash')]).mapped('current_balance'))
        current_revenue = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', current_month_start)]).mapped('amount_total')) + self._sum_pos_orders([('date_order', '>=', current_month_start)])
        previous_revenue = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', previous_month_start), ('invoice_date', '<', current_month_start)]).mapped('amount_total')) + self._sum_pos_orders([('date_order', '>=', previous_month_start), ('date_order', '<', current_month_start)])
        revenue_trend = (current_revenue - previous_revenue) / previous_revenue * 100 if previous_revenue else 100
        current_purchases = sum(self.env['purchase.order'].search([('state', 'in', ['purchase', 'done']), ('date_approve', '>=', current_month_start)]).mapped('amount_total'))
        previous_purchases = sum(self.env['purchase.order'].search([('state', 'in', ['purchase', 'done']), ('date_approve', '>=', previous_month_start), ('date_approve', '<', current_month_start)]).mapped('amount_total'))
        purchases_trend = (current_purchases - previous_purchases) / previous_purchases * 100 if previous_purchases else 100
        customer_receivables = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]).mapped('amount_residual'))
        deliveries_pending = self.env['stock.picking'].search_count([('picking_type_code', '=', 'outgoing'), ('state', 'not in', ['done', 'cancel'])])
        return {'cash_balance': cash_balance, 'gross_margin': gross_margin, 'revenue': current_revenue, 'revenue_trend': round(revenue_trend, 1), 'purchases': current_purchases, 'purchases_trend': round(purchases_trend, 1), 'receivables': customer_receivables, 'receivables_trend': 0, 'deliveries': deliveries_pending, 'deliveries_trend': 0}

    @api.model
    def get_top_unpaid_invoices(self, filters=None):
        domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]
        domain += self._get_date_domain(filters, 'invoice_date')
        invoices = self.env['account.move'].search(domain)
        customers = {}
        for invoice in invoices:
            partner = invoice.partner_id
            if partner.id not in customers:
                customers[partner.id] = {'id': partner.id, 'customer': partner.name, 'residual': 0, 'invoice_count': 0}
            customers[partner.id]['residual'] += invoice.amount_residual
            customers[partner.id]['invoice_count'] += 1
        result = sorted(customers.values(), key=lambda x: x['residual'], reverse=True)
        return result

    @api.model
    def get_top_reserved_products(self, filters=None):
        domain = [('picking_id.picking_type_code', '=', 'outgoing'), ('picking_id.state', 'not in', ['done', 'cancel'])]
        moves = self.env['stock.move'].search(domain)
        products = {}
        for move in moves:
            product = move.product_id
            customer = move.picking_id.partner_id.name or '-'
            if product.id not in products:
                products[product.id] = {'id': product.id, 'name': product.display_name, 'qty': 0, 'delivery_count': 0, 'customers': set(), 'picking_ids': set(), 'pickings': set()}
            products[product.id]['qty'] += move.product_uom_qty
            products[product.id]['delivery_count'] += 1
            products[product.id]['customers'].add(customer)
            products[product.id]['picking_ids'].add(move.picking_id.id)
            products[product.id]['pickings'].add(move.picking_id.name)
        for product in products.values():
            product['customer'] = ', '.join(list(product['customers'])[:3])
            product['picking_ids'] = list(product['picking_ids'])
            product['pickings'] = ', '.join(list(product['pickings'])[:3])
            del product['customers']
        result = sorted(products.values(), key=lambda x: x['qty'], reverse=True)
        return result

    @api.model
    def get_revenue_chart(self, filters=None):
        from collections import defaultdict
        from datetime import date
        filters = filters or {}
        period = filters.get('period', 'year')
        domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]
        domain += self._get_date_domain(filters, 'invoice_date')
        invoices = self.env['account.move'].search(domain)
        revenue_chart = defaultdict(float)
        receivable_chart = defaultdict(float)
        if period == 'year':
            labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
            for invoice in invoices:
                if not invoice.invoice_date:
                    continue
                month_index = invoice.invoice_date.month - 1
                revenue_chart[month_index] += invoice.amount_untaxed
                if invoice.payment_state in ['not_paid', 'partial']:
                    receivable_chart[month_index] += invoice.amount_residual
            revenue_values = [revenue_chart[i] for i in range(12)]
            receivable_values = [receivable_chart[i] for i in range(12)]
        else:
            today = date.today()
            labels = [str(day) for day in range(1, today.day + 1)]
            revenue_values = [0 for _ in labels]
            receivable_values = [0 for _ in labels]
            for invoice in invoices:
                if not invoice.invoice_date:
                    continue
                if invoice.invoice_date.month != today.month or invoice.invoice_date.year != today.year:
                    continue
                idx = invoice.invoice_date.day - 1
                revenue_values[idx] += invoice.amount_untaxed
                if invoice.payment_state in ['not_paid', 'partial']:
                    receivable_values[idx] += invoice.amount_residual
        if 'pos.order' in self.env.registry:
            pos_orders = self.env['pos.order'].search(self._get_date_domain(filters, 'date_order'))
            for order in pos_orders:
                if not order.date_order:
                    continue
                if period == 'year':
                    revenue_values[order.date_order.month - 1] += order.amount_total
                elif order.date_order.month == today.month and order.date_order.year == today.year:
                    idx = order.date_order.day - 1
                    if 0 <= idx < len(revenue_values):
                        revenue_values[idx] += order.amount_total
        return {'labels': labels, 'revenue': revenue_values, 'receivables': receivable_values, 'total_revenue': sum(revenue_values), 'total_receivables': sum(receivable_values)}

    @api.model
    def get_activity_chart(self):
        revenue = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]).mapped('amount_untaxed'))
        purchases = sum(self.env['purchase.order'].search([('state', 'in', ['purchase', 'done'])]).mapped('amount_untaxed'))
        receivables = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]).mapped('amount_residual'))
        reserved_stock = self.env['stock.move'].search_count([('picking_id.picking_type_code', '=', 'outgoing'), ('state', 'in', ['assigned', 'partially_available'])])
        return {'labels': ['CA', 'Achats', 'Créances', 'Réservations'], 'values': [revenue, purchases, receivables, reserved_stock]}

    def _get_date_domain(self, filters, field_name):
        filters = filters or {}
        period = filters.get('period', 'month')
        today = date.today()
        if period == 'today':
            return [(field_name, '>=', today), (field_name, '<=', today)]
        if period == 'week':
            start = today - timedelta(days=today.weekday())
            return [(field_name, '>=', start)]
        if period == 'month':
            start = today.replace(day=1)
            return [(field_name, '>=', start)]
        if period == 'year':
            start = today.replace(month=1, day=1)
            return [(field_name, '>=', start)]
        if period == 'custom':
            date_from = filters.get('date_from')
            date_to = filters.get('date_to')
            domain = []
            if date_from:
                domain.append((field_name, '>=', date_from))
            if date_to:
                domain.append((field_name, '<=', date_to))
            return domain
        return []

    @api.model
    def get_alerts(self):
        alerts = []
        invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])])
        partners = {}
        for invoice in invoices:
            partner = invoice.partner_id
            if partner.id not in partners:
                partners[partner.id] = {'id': partner.id, 'name': partner.name, 'amount': 0}
            partners[partner.id]['amount'] += invoice.amount_residual
        critical_clients = [p for p in partners.values() if p['amount'] >= 5000000]
        if critical_clients:
            alerts.append({'type': 'danger', 'title': 'Créances Critiques', 'count': len(critical_clients), 'amount': sum((x['amount'] for x in critical_clients)), 'items': sorted(critical_clients, key=lambda x: x['amount'], reverse=True)[:10]})
        overdue_items = []
        overdue_invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial']), ('invoice_date_due', '<', fields.Date.today())])
        for invoice in overdue_invoices:
            delay = (fields.Date.today() - invoice.invoice_date_due).days
            if delay > 60:
                level = 'critical'
            elif delay > 30:
                level = 'warning'
            else:
                level = 'normal'
            overdue_items.append({'id': invoice.id, 'name': invoice.name, 'customer': invoice.partner_id.name, 'amount': invoice.amount_residual, 'delay': delay, 'level': level})
        if overdue_items:
            alerts.append({'type': 'warning', 'title': 'Factures en Retard', 'count': len(overdue_items), 'items': overdue_items[:10]})
        blocked_items = []
        pickings = self.env['stock.picking'].search([('picking_type_code', '=', 'outgoing'), ('state', 'not in', ['done', 'cancel'])])
        today = fields.Date.today()
        for picking in pickings:
            if picking.scheduled_date:
                delay = (today - picking.scheduled_date.date()).days
                if delay >= 7:
                    blocked_items.append({'id': picking.id, 'name': picking.name, 'amount': delay})
        if blocked_items:
            alerts.append({'type': 'warning', 'title': 'Livraisons Bloquées', 'count': len(blocked_items), 'items': blocked_items[:10]})
        low_stock_items = []
        min_qty = self.env['primetech.reporting.settings'].get_values()['stock_min_alert_threshold']
        warning_qty = max(min_qty / 2.0, 1.0)
        products = self.env['product.product'].search([('active', '=', True), ('sale_ok', '=', True)])
        for product in products:
            qty = int(product.qty_available)
            if qty < min_qty:
                if qty <= 0:
                    level = 'critical'
                elif qty < warning_qty:
                    level = 'warning'
                else:
                    level = 'low'
                low_stock_items.append({'id': product.id, 'name': product.display_name, 'qty': qty, 'sale_price': product.lst_price, 'level': level, 'model': 'product.product'})
        low_stock_items = sorted(low_stock_items, key=lambda item: item['qty'])
        if low_stock_items:
            alerts.append({'type': 'low_stock', 'title': '⚠ Stock Faible', 'count': len(low_stock_items), 'items': low_stock_items})
        return alerts

    @api.model
    def get_receivables_chart(self, filters=None):
        current_year = fields.Date.today().year
        result = {}
        for month in range(1, 13):
            invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial']), ('invoice_date', '>=', date(current_year, month, 1)), ('invoice_date', '<=', date(current_year, month, monthrange(current_year, month)[1]))])
            result[month] = sum(invoices.mapped('amount_residual'))
        return {'labels': ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'], 'values': [result.get(i, 0) for i in range(1, 13)]}
