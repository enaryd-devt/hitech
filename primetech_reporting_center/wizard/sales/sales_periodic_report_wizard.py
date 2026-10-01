from odoo import fields, models
from datetime import datetime

class SalesPeriodicReportWizard(models.TransientModel):
    _name = 'primetech.sales.periodic.report.wizard'
    _description = 'Rapport Périodique des Ventes'
    date_from = fields.Date(string='Date début', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Commercial')
    partner_id = fields.Many2one('res.partner', string='Client')
    state_filter = fields.Selection([('all', 'Toutes les ventes'), ('sale', 'Commandes confirmées'), ('invoiced', 'Facturées')], string='État', default='all')

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['primetech.sales.periodic.report'].get_report_data(date_from=self.date_from, date_to=self.date_to, company_id=self.company_id.id, user_id=self.user_id.id if self.user_id else False, partner_id=self.partner_id.id if self.partner_id else False, state_filter=self.state_filter)
        html = self.env['ir.qweb']._render('primetech_reporting_center.sales_periodic_pdf', {'wizard': self, 'report_data': report_data, 'print_date': datetime.now().strftime('%d/%m/%Y %H:%M:%S'), 'generated_at': datetime.now()})
        preview = self.env['primetech.sales.preview.wizard'].create({'name': 'Rapport Périodique des Ventes', 'html': html.decode() if isinstance(html, bytes) else html, 'pdf_report_ref': 'primetech_reporting_center.sales_periodic_pdf_report', 'xlsx_report_ref': 'primetech_reporting_center.sales_periodic_xlsx_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu du Rapport', 'res_model': 'primetech.sales.preview.wizard', 'res_id': preview.id, 'view_mode': 'form', 'view_id': self.env.ref('primetech_reporting_center.view_sales_preview_wizard_form').id, 'target': 'current'}
