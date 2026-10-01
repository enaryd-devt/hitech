from odoo import api, models

class PrimetechGeneralLedger(models.AbstractModel):
    _name = 'primetech.general.ledger'
    _description = 'Grand Livre OHADA'

    @api.model
    def get_general_ledger(self, date_from, date_to, account_from=False, account_to=False, posted_only=True, hide_zero_balance=False):
        domain_accounts = [('deprecated', '=', False)]
        if account_from:
            domain_accounts.append(('code', '>=', account_from))
        if account_to:
            domain_accounts.append(('code', '<=', account_to))
        accounts = self.env['account.account'].search(domain_accounts, order='code')
        result = {'accounts': []}
        for account in accounts:
            move_domain = [('account_id', '=', account.id), ('date', '>=', date_from), ('date', '<=', date_to)]
            if posted_only:
                move_domain.append(('parent_state', '=', 'posted'))
            lines = self.env['account.move.line'].search(move_domain, order='date,id')
            opening_domain = [('account_id', '=', account.id), ('date', '<', date_from)]
            if posted_only:
                opening_domain.append(('parent_state', '=', 'posted'))
            opening_lines = self.env['account.move.line'].search(opening_domain)
            opening_balance = sum(opening_lines.mapped('debit')) - sum(opening_lines.mapped('credit'))
            running_balance = opening_balance
            account_lines = []
            total_debit = 0.0
            total_credit = 0.0
            for line in lines:
                running_balance += line.debit - line.credit
                total_debit += line.debit
                total_credit += line.credit
                account_lines.append({'date': line.date.strftime('%d/%m/%Y') if line.date else '', 'journal': line.journal_id.code or '', 'piece': line.move_id.name or '', 'label': line.name or line.move_id.ref or '', 'letter': getattr(line, 'matching_number', '') or '', 'debit': line.debit, 'credit': line.credit, 'balance': running_balance})
            closing_balance = running_balance
            if hide_zero_balance and (not account_lines) and (opening_balance == 0):
                continue
            result['accounts'].append({'code': account.code, 'name': account.name, 'opening_balance': opening_balance, 'lines': account_lines, 'total_debit': total_debit, 'total_credit': total_credit, 'closing_balance': closing_balance})
        return result
