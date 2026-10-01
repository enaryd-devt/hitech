from odoo import api, models
from .ohada_mapping import OHADA_ACTIF, OHADA_PASSIF

class PrimetechBalanceSheet(models.AbstractModel):
    _name = 'primetech.balance.sheet'
    _description = 'Bilan OHADA'

    @api.model
    def get_balance_sheet(self, date_to, posted_only=True):
        domain = [('date', '<=', date_to)]
        if posted_only:
            domain.append(('parent_state', '=', 'posted'))
        move_lines = self.env['account.move.line'].search(domain)
        balances = {}
        for line in move_lines:
            code = line.account_id.code or ''
            balances.setdefault(code, {'debit': 0.0, 'credit': 0.0})
            balances[code]['debit'] += line.debit
            balances[code]['credit'] += line.credit
        actif = self._build_section(OHADA_ACTIF, balances, asset=True)
        passif = self._build_section(OHADA_PASSIF, balances, asset=False)
        total_actif = sum((l.get('net', 0) for l in actif if l.get('line_type') == 'line'))
        total_passif = sum((l.get('net', 0) for l in passif if l.get('line_type') == 'line'))
        return {'actif': actif, 'passif': passif, 'total_actif': total_actif, 'total_passif': total_passif}

    def _build_section(self, mapping, balances, asset=True):
        result = []
        running_total = 0
        for item in mapping:
            if item.get('type') == 'total':
                result.append({'line_type': 'total', 'ref': item['ref'], 'label': item['label'], 'brut': running_total, 'amort': 0.0, 'net': running_total, 'net_n1': 0.0})
                continue
            if item.get('type') == 'grand_total':
                result.append({'line_type': 'grand_total', 'ref': item['ref'], 'label': item['label'], 'brut': running_total, 'amort': 0.0, 'net': running_total, 'net_n1': 0.0})
                continue
                result.append({'line_type': 'total', 'ref': item['ref'], 'label': item['label']})
                continue
            if item.get('type') == 'grand_total':
                result.append({'line_type': 'grand_total', 'ref': item['ref'], 'label': item['label']})
                continue
            brut = 0.0
            amort = 0.0
            for prefix in item.get('accounts', []):
                for account_code, vals in balances.items():
                    if account_code.startswith(prefix):
                        brut += vals['debit'] - vals['credit']
            net = brut - amort
            if not asset:
                net = abs(net)
            running_total += net
            result.append({'line_type': 'line', 'ref': item['ref'], 'label': item['label'], 'note': '', 'brut': brut, 'amort': amort, 'net': net, 'net_n1': 0.0})
        return result
