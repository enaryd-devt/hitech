from datetime import datetime
from odoo import fields, models

class BalanceSheetWizard(models.TransientModel):
    _name = 'primetech.balance.sheet.wizard'
    _description = 'Bilan OHADA'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: datetime.today().replace(month=1, day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    posted_only = fields.Boolean(string='Écritures validées uniquement', default=True)
    display_mode = fields.Selection([('actif', 'Actif uniquement'), ('passif', 'Passif uniquement'), ('both', 'Actif + Passif')], string='Affichage', default='both', required=True)

    def action_open_report(self):
        self.ensure_one()
        report_data = self.env['primetech.balance.sheet'].get_balance_sheet(date_to=self.date_to, posted_only=self.posted_only)
        generated_at = fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        html = str(self.env['ir.qweb']._render('primetech_reporting_center.balance_sheet_template', {'data': report_data, 'display_mode': self.display_mode, 'date_to': self.date_to, 'generated_at': generated_at, 'wizard': self}))
        preview = self.env['primetech.report.preview.wizard'].create({'name': 'Bilan OHADA', 'html_content': html, 'report_xmlid': 'primetech_reporting_center.action_balance_sheet_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Prévisualisation', 'res_model': 'primetech.report.preview.wizard', 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_report_preview_wizard').id, 'res_id': preview.id, 'target': 'current'}

    def action_export_excel(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_balance_sheet_xlsx').report_action(self, data={'date_to': self.date_to, 'posted_only': self.posted_only})

    def action_print(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_balance_sheet_report').report_action(self, data={'date_to': self.date_to, 'posted_only': self.posted_only, 'display_mode': self.display_mode})
