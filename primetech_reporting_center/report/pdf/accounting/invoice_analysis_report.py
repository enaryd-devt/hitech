from datetime import datetime
from odoo import models

class InvoiceAnalysisPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.invoice_analysis_pdf_template'
    _description = 'Analyse de Facturation PDF'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.invoice.analysis.report.wizard'].browse(docids)
        wizard.ensure_one()
        report_data = self.env['primetech.invoice.analysis.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, partner_id=wizard.partner_id.id if wizard.partner_id else False, user_id=wizard.user_id.id if wizard.user_id else False, move_type=wizard.move_type, payment_state=wizard.payment_state)
        return {'doc_ids': wizard.ids, 'doc_model': 'primetech.invoice.analysis.report.wizard', 'docs': wizard, 'wizard': wizard, 'report_data': report_data, 'generated_at': datetime.now()}
