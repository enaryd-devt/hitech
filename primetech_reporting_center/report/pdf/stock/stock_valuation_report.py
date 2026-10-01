# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models

class ReportStockValuation(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_valuation_pdf_template'
    _description = 'Stock Valuation PDF Report'

    def _get_report_values(self, docids, data=None):
        filters = {}
        if data:
            filters = data.get('filters', {})
        wizard = self.env['pt.stock.valuation.wizard']
        report_data = self.env['pt.stock.valuation'].get_report_data(filters)
        return {'docs': wizard, 'wizard': wizard, 'filters': filters, 'report_data': report_data, 'generated_at': datetime.now()}
