from datetime import datetime
from odoo import fields, models

class PartnerBalanceWizard(models.TransientModel):
    _name = 'primetech.partner.balance.wizard'
    _description = 'Balance des Tiers'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: datetime.today().replace(month=1, day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    partner_type = fields.Selection([('customer', 'Clients'), ('supplier', 'Fournisseurs'), ('both', 'Clients & Fournisseurs')], string='Type de tiers', default='both', required=True)
    posted_only = fields.Boolean(string='Écritures validées uniquement', default=True)

    def action_open_report(self):
        self.ensure_one()
        report_data = self.env['primetech.partner.balance'].get_partner_balance(date_from=self.date_from, date_to=self.date_to, partner_type=self.partner_type, posted_only=self.posted_only)
        generated_at = fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        html = str(self.env['ir.qweb']._render('primetech_reporting_center.partner_balance_template', {'data': report_data, 'date_from': self.date_from, 'date_to': self.date_to, 'generated_at': generated_at, 'wizard': self}))
        preview = self.env['primetech.report.preview.wizard'].create({'name': 'Balance des Tiers', 'html_content': html, 'report_xmlid': 'primetech_reporting_center.action_partner_balance_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Prévisualisation', 'res_model': 'primetech.report.preview.wizard', 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_report_preview_wizard').id, 'res_id': preview.id, 'target': 'current'}

    def action_export_excel(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_partner_balance_xlsx').report_action(self, data={'date_from': self.date_from, 'date_to': self.date_to, 'partner_type': self.partner_type, 'posted_only': self.posted_only})
