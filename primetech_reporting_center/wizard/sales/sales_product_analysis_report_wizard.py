from datetime import datetime
from odoo import fields, models

class SalesProductAnalysisReportWizard(models.TransientModel):
    _name = 'primetech.sales.product.analysis.report.wizard'
    _description = 'Analyse Produits'
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Commercial')
    product_id = fields.Many2one('product.product', string='Produit')

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['primetech.sales.product.analysis.report'].get_report_data(date_from=self.date_from, date_to=self.date_to, company_id=self.company_id.id, user_id=self.user_id.id if self.user_id else False, product_id=self.product_id.id if self.product_id else False)
        html = self.env['ir.qweb']._render('primetech_reporting_center.sales_product_analysis_preview', {'wizard': self, 'report_data': report_data, 'generated_at': datetime.now()})
        preview = self.env['primetech.sales.preview.wizard'].create({'name': 'Analyse Produits', 'html': html.decode() if isinstance(html, bytes) else html, 'pdf_report_ref': 'primetech_reporting_center.sales_product_analysis_pdf_report', 'xlsx_report_ref': 'primetech_reporting_center.sales_product_analysis_xlsx_report', 'wizard_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'primetech.sales.preview.wizard', 'view_mode': 'form', 'res_id': preview.id, 'target': 'current'}

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.sales_product_analysis_xlsx_report').report_action(self)
