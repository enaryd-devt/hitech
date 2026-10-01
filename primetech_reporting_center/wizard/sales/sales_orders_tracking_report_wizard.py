from datetime import datetime
from odoo import fields
from odoo import models

class SalesOrdersTrackingReportWizard(models.TransientModel):
    _name = 'primetech.sales.orders.tracking.report.wizard'
    _description = 'Suivi des Commandes'
    date_from = fields.Date(string='Date début', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Commercial')
    partner_id = fields.Many2one('res.partner', string='Client')
    state = fields.Selection([('draft', 'Brouillon'), ('sent', 'Devis envoyé'), ('sale', 'Commande confirmée'), ('done', 'Terminée'), ('cancel', 'Annulée')], string='Etat')

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['primetech.sales.orders.tracking.report'].get_report_data(date_from=self.date_from, date_to=self.date_to, company_id=self.company_id.id, user_id=self.user_id.id if self.user_id else False, partner_id=self.partner_id.id if self.partner_id else False, state=self.state)
        html = self.env['ir.qweb']._render('primetech_reporting_center.sales_orders_tracking_preview', {'wizard': self, 'report_data': report_data, 'generated_at': datetime.now()})
        preview = self.env['primetech.sales.preview.wizard'].create({'name': 'Suivi des Commandes', 'html': html.decode() if isinstance(html, bytes) else html, 'pdf_report_ref': 'primetech_reporting_center.sales_orders_tracking_pdf_report', 'xlsx_report_ref': 'primetech_reporting_center.sales_orders_tracking_xlsx_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'primetech.sales.preview.wizard', 'view_mode': 'form', 'res_id': preview.id, 'target': 'current'}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.sales_orders_tracking_pdf_report').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.sales_orders_tracking_xlsx_report').report_action(self)
