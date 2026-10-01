# -*- coding: utf-8 -*-
from odoo import api, models

class PurchaseExpensePdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.purchase_expense_pdf'
    _description = 'Purchase Expense PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        filters = data.get('filters', {})
        report_data = self.env['primetech.purchase.expense.report'].get_report_data(filters)
        return {'doc_ids': docids, 'doc_model': 'primetech.purchase.expense.wizard', 'data': report_data, 'filters': filters}
