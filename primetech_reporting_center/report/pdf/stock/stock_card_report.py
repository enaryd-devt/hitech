# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models

class ReportStockCard(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_card_pdf_template'
    _description = 'Stock Card PDF Report'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['pt.stock.card.wizard'].browse(docids[:1])
        filters = {}
        if data:
            filters = data.get('filters', {})
        report_data = self.env['pt.stock.card'].get_report_data(filters)
        filters = data.get('filters', {}) if data else {}
        report_data = self.env['pt.stock.card'].get_report_data(filters)
        return {'docs': wizard, 'wizard': wizard, 'filters': filters, 'report_data': report_data, 'generated_at': datetime.now()}
