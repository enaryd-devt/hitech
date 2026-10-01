# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models

class CashPeriodReport(models.TransientModel):
    _name = 'pt.cash.period'
    _description = 'Periodic Cash Report'

    def get_report_data(self, filters):
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        journal_ids = filters.get('journal_ids', [])
        movements = []
        journal_summary = defaultdict(lambda: {'journal': '', 'opening': 0.0, 'incoming': 0.0, 'outgoing': 0.0, 'net': 0.0, 'closing': 0.0})
        total_incoming = 0.0
        total_outgoing = 0.0
        payment_domain = [('state', '=', 'posted'), ('date', '>=', date_from), ('date', '<=', date_to)]
        if journal_ids:
            payment_domain.append(('journal_id', 'in', journal_ids))
        payments = self.env['account.payment'].search(payment_domain, order='date,id')
        for payment in payments:
            journal = payment.journal_id.name or '-'
            summary = journal_summary[journal]
            summary['journal'] = journal
            if payment.payment_type == 'inbound':
                movement_type = 'Encaissement'
                amount = payment.amount
                total_incoming += amount
                summary['incoming'] += amount
            else:
                movement_type = 'Décaissement'
                amount = payment.amount
                total_outgoing += amount
                summary['outgoing'] += amount
            movements.append({'date': payment.date, 'journal': journal, 'reference': payment.name or '', 'partner': payment.partner_id.name or '', 'type': movement_type, 'nature': 'Paiement', 'amount': amount})
        statement_domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        statement_lines = self.env['account.bank.statement.line'].search(statement_domain, order='date,id')
        for line in statement_lines:
            journal = ''
            if hasattr(line, 'journal_id') and line.journal_id:
                journal = line.journal_id.name
            elif hasattr(line, 'statement_id') and line.statement_id:
                journal = line.statement_id.journal_id.name
            else:
                journal = 'Journal inconnu'
            summary = journal_summary[journal]
            summary['journal'] = journal
            amount = abs(line.amount)
            if line.amount >= 0:
                movement_type = 'Encaissement'
                total_incoming += amount
                summary['incoming'] += amount
            else:
                movement_type = 'Décaissement'
                total_outgoing += amount
                summary['outgoing'] += amount
            movements.append({'date': line.date, 'journal': journal, 'reference': line.payment_ref or '', 'partner': line.partner_id.name if line.partner_id else '', 'type': movement_type, 'nature': 'Relevé bancaire', 'amount': amount})
        journals = self.env['account.journal']
        if journal_ids:
            journals = journals.browse(journal_ids)
        else:
            journals = journals.search([('type', 'in', ['bank', 'cash'])])
        for journal in journals:
            opening = 0.0
            opening_payments = self.env['account.payment'].search([('state', '=', 'posted'), ('journal_id', '=', journal.id), ('date', '<', date_from)])
            for pay in opening_payments:
                if pay.payment_type == 'inbound':
                    opening += pay.amount
                else:
                    opening -= pay.amount
            opening_statements = self.env['account.bank.statement.line'].search([('date', '<', date_from)])
            for st in opening_statements:
                st_journal = False
                if hasattr(st, 'journal_id'):
                    st_journal = st.journal_id
                elif hasattr(st, 'statement_id'):
                    st_journal = st.statement_id.journal_id
                if st_journal and st_journal.id == journal.id:
                    opening += st.amount
            summary = journal_summary[journal.name]
            summary['journal'] = journal.name
            summary['opening'] = opening
        for summary in journal_summary.values():
            summary['net'] = summary['incoming'] - summary['outgoing']
            summary['closing'] = summary['opening'] + summary['net']
        opening_total = sum((x['opening'] for x in journal_summary.values()))
        closing_total = sum((x['closing'] for x in journal_summary.values()))
        kpi = {'opening_balance': opening_total, 'incoming': total_incoming, 'outgoing': total_outgoing, 'net': total_incoming - total_outgoing, 'closing_balance': closing_total}
        movements.sort(key=lambda x: (x['date'], x['journal']))
        return {'kpi': kpi, 'movements': movements, 'journal_summary': sorted(journal_summary.values(), key=lambda x: x['journal'])}
