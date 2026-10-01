from odoo import api, models

class PrimetechAccountingJournal(models.AbstractModel):
    _name = 'primetech.accounting.journal'
    _description = 'Journaux Comptables'

    @api.model
    def get_journals_report(self, date_from, date_to, journal_ids=False, posted_only=True):
        journals_domain = []
        if journal_ids:
            journals_domain.append(('id', 'in', journal_ids))
        journals = self.env['account.journal'].search(journals_domain, order='code')
        result = {'journals': []}
        for journal in journals:
            domain = [('journal_id', '=', journal.id), ('date', '>=', date_from), ('date', '<=', date_to)]
            if posted_only:
                domain.append(('parent_state', '=', 'posted'))
            lines = self.env['account.move.line'].search(domain, order='date,move_id,id')
            entries = []
            total_debit = 0.0
            total_credit = 0.0
            for line in lines:
                total_debit += line.debit
                total_credit += line.credit
                entries.append({'date': line.date.strftime('%d/%m/%Y') if line.date else '', 'move': line.move_id.name or '', 'partner': line.partner_id.name or '', 'account': line.account_id.code or '', 'account_name': line.account_id.name or '', 'label': line.name or line.move_id.ref or '', 'debit': line.debit, 'credit': line.credit})
            if not entries:
                continue
            result['journals'].append({'journal_code': journal.code, 'journal_name': journal.name, 'entries': entries, 'total_debit': total_debit, 'total_credit': total_credit})
        return result
