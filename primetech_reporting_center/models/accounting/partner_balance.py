from odoo import api, models

class PrimetechPartnerBalance(models.AbstractModel):
    _name = 'primetech.partner.balance'
    _description = 'Balance des Tiers'

    @api.model
    def get_partner_balance(self, date_from, date_to, partner_type='both', posted_only=True):
        partner_domain = []
        if partner_type == 'customer':
            partner_domain.append(('customer_rank', '>', 0))
        elif partner_type == 'supplier':
            partner_domain.append(('supplier_rank', '>', 0))
        partners = self.env['res.partner'].search(partner_domain, order='name')
        result = {'partners': [], 'total_opening_debit': 0.0, 'total_opening_credit': 0.0, 'total_debit': 0.0, 'total_credit': 0.0, 'total_closing_debit': 0.0, 'total_closing_credit': 0.0}
        for partner in partners:
            opening_domain = [('partner_id', '=', partner.id), ('date', '<', date_from), ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable'])]
            if posted_only:
                opening_domain.append(('parent_state', '=', 'posted'))
            opening_lines = self.env['account.move.line'].search(opening_domain)
            opening_balance = sum(opening_lines.mapped('debit')) - sum(opening_lines.mapped('credit'))
            move_domain = [('partner_id', '=', partner.id), ('date', '>=', date_from), ('date', '<=', date_to), ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable'])]
            if posted_only:
                move_domain.append(('parent_state', '=', 'posted'))
            move_lines = self.env['account.move.line'].search(move_domain)
            period_debit = sum(move_lines.mapped('debit'))
            period_credit = sum(move_lines.mapped('credit'))
            closing_balance = opening_balance + period_debit - period_credit
            if opening_balance == 0 and period_debit == 0 and (period_credit == 0):
                continue
            opening_debit = opening_balance if opening_balance > 0 else 0
            opening_credit = abs(opening_balance) if opening_balance < 0 else 0
            closing_debit = closing_balance if closing_balance > 0 else 0
            closing_credit = abs(closing_balance) if closing_balance < 0 else 0
            result['partners'].append({'partner_id': partner.id, 'partner_name': partner.name or '', 'opening_debit': opening_debit, 'opening_credit': opening_credit, 'period_debit': period_debit, 'period_credit': period_credit, 'closing_debit': closing_debit, 'closing_credit': closing_credit})
            result['total_opening_debit'] += opening_debit
            result['total_opening_credit'] += opening_credit
            result['total_debit'] += period_debit
            result['total_credit'] += period_credit
            result['total_closing_debit'] += closing_debit
            result['total_closing_credit'] += closing_credit
        return result
