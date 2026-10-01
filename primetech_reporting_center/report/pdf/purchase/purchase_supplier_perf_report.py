# -*- coding: utf-8 -*-
from odoo import models

class PurchaseSupplierPerformancePdf(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_supplier_perf_pdf'
    _description = 'Purchase Supplier Performance PDF'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['pt.purchase.supp'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'pt.purchase.supp.wiz', 'filters': filters, 'report_data': report_data}
