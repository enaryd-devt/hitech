# -*- coding: utf-8 -*-
from odoo import models

class CashPeriodPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.cash_period_pdf'
    _description = 'Periodic Cash PDF Report'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['pt.cash.period.wiz'].browse(docids[:1])
        if not wizard:
            active_id = self.env.context.get('active_id')
            wizard = self.env['pt.cash.period.wiz'].browse(active_id)
        filters = wizard._prepare_filters()
        report_data = self.env['pt.cash.period'].get_report_data(filters)
        journal_names = ''
        if filters.get('journal_ids'):
            journals = self.env['account.journal'].browse(filters['journal_ids'])
            journal_names = ', '.join(journals.mapped('name'))
        else:
            journal_names = 'Tous les journaux'
        return {'doc_ids': wizard.ids, 'doc_model': 'pt.cash.period.wiz', 'docs': wizard, 'wizard': wizard, 'filters': filters, 'journal_names': journal_names, 'data': report_data}
