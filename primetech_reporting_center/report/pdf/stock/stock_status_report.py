# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models

class StockStatusPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_status_pdf_template'
    _description = 'Etat de Stock PDF'

    def _get_report_values(self, docids, data=None):
        filters = data.get('filters', {}) if data else {}
        report_data = self.env['pt.stock.status'].get_report_data(filters)
        return {'filters': filters, 'report_data': report_data, 'generated_at': datetime.now()}
