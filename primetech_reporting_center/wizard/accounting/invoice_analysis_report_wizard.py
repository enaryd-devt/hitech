from datetime import datetime
from odoo import fields
from odoo import models

class InvoiceAnalysisReportWizard(models.TransientModel):
    _name = 'primetech.invoice.analysis.report.wizard'
    _description = 'Analyse de Facturation'
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Client')
    user_id = fields.Many2one('res.users', string='Commercial')
    move_type = fields.Selection([('out_invoice', 'Facture Client'), ('out_refund', 'Avoir Client')], string='Type')
    payment_state = fields.Selection([('not_paid', 'Non Payée'), ('partial', 'Partiellement Payée'), ('paid', 'Payée'), ('in_payment', 'En Paiement'), ('reversed', 'Extournée')], string='Etat Paiement')

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['primetech.invoice.analysis.report'].get_report_data(date_from=self.date_from, date_to=self.date_to, company_id=self.company_id.id, partner_id=self.partner_id.id if self.partner_id else False, user_id=self.user_id.id if self.user_id else False, move_type=self.move_type, payment_state=self.payment_state)
        html = self.env['ir.qweb']._render('primetech_reporting_center.invoice_analysis_preview', {'wizard': self, 'report_data': report_data, 'generated_at': datetime.now()})
        preview = self.env['primetech.sales.preview.wizard'].create({'name': 'Analyse de Facturation', 'html': html.decode() if isinstance(html, bytes) else html, 'pdf_report_ref': 'primetech_reporting_center.invoice_analysis_pdf_report', 'xlsx_report_ref': 'primetech_reporting_center.invoice_analysis_xlsx_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'primetech.sales.preview.wizard', 'view_mode': 'form', 'res_id': preview.id, 'target': 'current'}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.invoice_analysis_pdf_report').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.invoice_analysis_xlsx_report').report_action(self)
