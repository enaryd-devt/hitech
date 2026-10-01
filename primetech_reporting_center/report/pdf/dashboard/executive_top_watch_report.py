# -*- coding: utf-8 -*-
from odoo import models


class ExecutiveTopWatchPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.executive_top_watch_pdf'
    _description = 'Executive Top Watch PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        report_data = self.env['primetech.dashboard'].get_top_watch_report_data(
            data.get('filters'), data.get('rows')
        )
        company = self.env['res.company'].browse(docids[:1]).exists() if docids else self.env.company
        company = company or self.env.company
        return {
            'doc_ids': docids,
            'doc_model': 'res.company',
            'docs': company,
            'company': company,
            'report_data': report_data,
        }
