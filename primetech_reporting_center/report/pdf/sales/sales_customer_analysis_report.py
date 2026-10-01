from datetime import datetime
from odoo import models

class SalesCustomerAnalysisPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_customer_analysis_pdf'
    _description = 'Analyse Clients PDF'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.sales.customer.analysis.report.wizard'].browse(docids)
        wizard.ensure_one()
        report_data = self.env['primetech.sales.customer.analysis.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False)
        return {'doc_ids': wizard.ids, 'doc_model': 'primetech.sales.customer.analysis.report.wizard', 'docs': wizard, 'wizard': wizard, 'company': wizard.company_id, 'report_data': report_data, 'generated_at': datetime.now()}
