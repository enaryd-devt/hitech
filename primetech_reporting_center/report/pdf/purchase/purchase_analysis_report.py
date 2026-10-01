# -*- coding: utf-8 -*-
from odoo import api, models

class PurchaseAnalysisPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_analysis_pdf'
    _description = 'Purchase Analysis PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['primetech.purchase.analysis.report'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'purchase.order', 'data': report_data, 'filters': filters}
