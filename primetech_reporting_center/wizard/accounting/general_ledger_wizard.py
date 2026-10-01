from odoo import fields, models
from datetime import datetime

class GeneralLedgerWizard(models.TransientModel):
    _name = 'primetech.general.ledger.wizard'
    _description = 'Grand Livre OHADA'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: datetime.today().replace(month=1, day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    account_from_id = fields.Many2one('account.account', string='Compte début')
    account_to_id = fields.Many2one('account.account', string='Compte fin')
    posted_only = fields.Boolean(string='Écritures validées uniquement', default=True)
    hide_zero_balance = fields.Boolean(string='Masquer comptes sans mouvement', default=False)

    def action_open_report(self):
        self.ensure_one()
        ledger_data = self.env['primetech.general.ledger'].get_general_ledger(date_from=self.date_from, date_to=self.date_to, account_from=self.account_from_id.code if self.account_from_id else False, account_to=self.account_to_id.code if self.account_to_id else False, posted_only=self.posted_only, hide_zero_balance=self.hide_zero_balance)
        generated_at = fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        html = str(self.env['ir.qweb']._render('primetech_reporting_center.gl_report_template', {'data': ledger_data, 'date_from': self.date_from, 'date_to': self.date_to, 'generated_at': generated_at}))
        import json
        preview = self.env['primetech.report.preview.wizard'].create({'name': 'Grand Livre OHADA', 'html_content': html, 'report_xmlid': 'primetech_reporting_center.action_general_ledger_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Prévisualisation Grand Livre', 'res_model': 'primetech.report.preview.wizard', 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_report_preview_wizard').id, 'res_id': preview.id, 'target': 'current'}

    def action_export_excel(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_general_ledger_xlsx').report_action(self, data={'date_from': self.date_from, 'date_to': self.date_to, 'account_from': self.account_from_id.code if self.account_from_id else False, 'account_to': self.account_to_id.code if self.account_to_id else False, 'posted_only': self.posted_only, 'hide_zero_balance': self.hide_zero_balance})
