# -*- coding: utf-8 -*-
from odoo import api, models


class PrimeTechHRReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.hr_report_pdf_document'
    _description = 'Rapport Ressources Humaines'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['primetech.hr.report.wizard'].browse(docids)
        if not docs and data and data.get('docids'):
            docs = self.env['primetech.hr.report.wizard'].browse(data['docids'])
        return {
            'doc_ids': docs.ids,
            'doc_model': 'primetech.hr.report.wizard',
            'docs': docs,
        }
