# -*- coding: utf-8 -*-
from odoo import models

class PurchaseBillPdf(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_bill_pdf'
    _description = 'Purchase Vendor Bills PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['pt.purchase.bill'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'pt.purchase.bill.wiz', 'filters': filters, 'report_data': report_data}
