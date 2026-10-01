# -*- coding: utf-8 -*-
from odoo import models


class ExecutiveCashflowPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.executive_cashflow_pdf'
    _description = 'Executive Cashflow PDF Report'

    def _get_report_values(self, docids, data=None):
        filters = (data or {}).get('filters', {})
        report_data = self.env['primetech.dashboard'].get_cashflow_report_data(filters)
        company = self.env['res.company'].browse(docids[:1]).exists() if docids else self.env.company
        company = company or self.env.company
        return {
            'doc_ids': docids,
            'doc_model': 'res.company',
            'docs': company,
            'company': company,
            'report_data': report_data,
        }
