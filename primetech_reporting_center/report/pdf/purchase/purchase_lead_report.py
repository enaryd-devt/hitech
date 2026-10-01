# -*- coding: utf-8 -*-
from odoo import models

class PurchaseLeadPdf(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_lead_pdf'
    _description = 'Purchase Lead Time PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['pt.purchase.lead'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'pt.purchase.lead.wiz', 'filters': filters, 'report_data': report_data}
