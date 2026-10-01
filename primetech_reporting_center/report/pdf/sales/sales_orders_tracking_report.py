from datetime import datetime
from odoo import models

class SalesOrdersTrackingPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.sales_orders_tracking'
    _description = 'Suivi des Commandes PDF'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.sales.orders.tracking.report.wizard'].browse(docids)
        wizard.ensure_one()
        report_data = self.env['primetech.sales.orders.tracking.report'].get_report_data(date_from=wizard.date_from, date_to=wizard.date_to, company_id=wizard.company_id.id, user_id=wizard.user_id.id if wizard.user_id else False, partner_id=wizard.partner_id.id if wizard.partner_id else False, state=wizard.state)
        return {'docs': wizard, 'wizard': wizard, 'report_data': report_data, 'generated_at': datetime.now()}
