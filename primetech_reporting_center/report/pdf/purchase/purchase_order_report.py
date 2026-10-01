# -*- coding: utf-8 -*-
from odoo import models

class PurchaseOrderPdf(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_order_pdf'
    _description = 'Purchase Orders PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['pt.purchase.order'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'pt.purchase.order.wiz', 'data': report_data, 'filters': filters}
