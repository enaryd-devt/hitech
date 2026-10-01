from odoo import fields, models

class AccountingJournalWizard(models.TransientModel):
    _name = 'primetech.accounting.journal.wizard'
    _description = 'Journaux Comptables'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.context_today)
    journal_ids = fields.Many2many('account.journal', string='Journaux')
    posted_only = fields.Boolean(string='Écritures validées uniquement', default=True)

    def action_open_report(self):
        self.ensure_one()
        data = self.env['primetech.accounting.journal'].get_journals_report(date_from=self.date_from, date_to=self.date_to, journal_ids=self.journal_ids.ids, posted_only=self.posted_only)
        generated_at = fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        html = str(self.env['ir.qweb']._render('primetech_reporting_center.accounting_journal_template', {'data': data, 'date_from': self.date_from, 'date_to': self.date_to, 'generated_at': generated_at}))
        preview = self.env['primetech.report.preview.wizard'].create({'name': 'Journaux Comptables', 'html_content': html, 'report_xmlid': 'primetech_reporting_center.action_accounting_journal_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Prévisualisation', 'res_model': 'primetech.report.preview.wizard', 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_report_preview_wizard').id, 'res_id': preview.id, 'target': 'current'}

    def action_export_excel(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_accounting_journal_xlsx').report_action(self, data={'date_from': self.date_from, 'date_to': self.date_to, 'journal_ids': self.journal_ids.ids, 'posted_only': self.posted_only})
