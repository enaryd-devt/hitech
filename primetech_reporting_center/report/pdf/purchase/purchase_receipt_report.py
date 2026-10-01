# -*- coding: utf-8 -*-
from odoo import models

class PurchaseReceiptPdf(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_receipt_pdf'
    _description = 'Purchase Receipts PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['pt.purchase.recv'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'pt.purchase.recv.wiz', 'filters': filters, 'report_data': report_data}
