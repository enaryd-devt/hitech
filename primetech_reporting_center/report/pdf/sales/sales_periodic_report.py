from datetime import datetime
from odoo import models
import logging
_logger = logging.getLogger(__name__)

class SalesPeriodicPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_periodic_pdf'
    _description = 'Rapport PDF Périodique des Ventes'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.sales.periodic.report.wizard'].browse(docids)
        if not wizard:
            return {'docs': [], 'report_data': {}}
        wizard.ensure_one()
        report_data = self.env['primetech.sales.periodic.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False, state_filter=wizard.state_filter)
        return {'doc_ids': wizard.ids, 'doc_model': 'primetech.sales.periodic.report.wizard', 'docs': wizard, 'wizard': wizard, 'company': wizard.company_id, 'currency': wizard.company_id.currency_id, 'generated_by': self.env.user, 'generated_at': datetime.now(), 'report_data': report_data}
