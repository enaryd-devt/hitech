# -*- coding: utf-8 -*-
from odoo import api, models

class PurchaseSupplierPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_supplier_pdf'
    _description = 'Purchase Supplier PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['primetech.purchase.supplier.report'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'purchase.order', 'data': report_data, 'filters': filters}
