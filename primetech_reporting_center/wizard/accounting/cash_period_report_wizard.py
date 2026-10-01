# -*- coding: utf-8 -*-
from odoo import fields, models

class CashPeriodReportWizard(models.TransientModel):
    _name = 'pt.cash.period.wiz'
    _description = 'Periodic Cash Report Wizard'
    date_from = fields.Date(string='Date début', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    journal_ids = fields.Many2many('account.journal', string='Journaux')
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {'date_from': self.date_from, 'date_to': self.date_to, 'company_id': self.company_id.id, 'journal_ids': self.journal_ids.ids, 'observations': self.observations}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        journal_names = ''
        if self.journal_ids:
            journal_names = ', '.join(self.journal_ids.mapped('name'))
        else:
            journal_names = 'Tous les journaux'
        report_data = self.env['pt.cash.period'].get_report_data(filters)
        html = self.env['ir.qweb']._render('primetech_reporting_center.cash_period_preview_template', {'data': report_data, 'filters': filters, 'journal_names': journal_names, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Rapport Périodique de Trésorerie', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_cash_period_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_cash_period_xlsx', 'wizard_id': self.id, 'wizard_model': 'pt.cash.period.wiz'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_cash_period_pdf').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_cash_period_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_accounting_dashboard'}
