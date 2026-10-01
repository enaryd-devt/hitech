from odoo import fields, models
from datetime import datetime

class TrialBalanceWizard(models.TransientModel):
    _name = 'primetech.trial.balance.wizard'
    _description = 'Balance Générale'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: datetime.today().replace(month=1, day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    level = fields.Selection([('1', 'Niveau 1 Chiffre'), ('2', 'Niveau 2 Chiffres'), ('3', 'Niveau 3 Chiffres'), ('4', 'Tous Niveaux')], string='Niveau', default='4', required=True)
    posted_only = fields.Boolean(string='Écritures validées uniquement', default=True)

    def action_open_report(self):
        self.ensure_one()
        data = self.env['primetech.trial.balance'].get_trial_balance(self.date_from, self.date_to, self.level, self.posted_only)
        previous_year = self.date_from.year - 1 if self.date_from else ''
        generated_at = datetime.now().strftime('%d/%m/%Y %H:%M')
        html = str(self.env['ir.qweb']._render('primetech_reporting_center.trial_balance_report_template', {'data': data, 'date_from': self.date_from, 'date_to': self.date_to, 'wizard': self, 'generated_at': generated_at, 'previous_year': previous_year}))
        preview = self.env['primetech.report.preview.wizard'].create({'name': 'Balance Générale OHADA', 'html_content': html, 'report_xmlid': 'primetech_reporting_center.action_trial_balance_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Prévisualisation', 'res_model': 'primetech.report.preview.wizard', 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_report_preview_wizard').id, 'res_id': preview.id, 'target': 'current'}

    def action_export_excel(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_trial_balance_xlsx').report_action(self, data={'date_from': self.date_from, 'date_to': self.date_to, 'level': self.level, 'posted_only': self.posted_only})
