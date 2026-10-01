from odoo import api, fields, models

class AccountingJournalReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.accounting_journal_template'
    _description = 'Journaux Comptables PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.accounting.journal.wizard'].browse(docids)
        report_data = self.env['primetech.accounting.journal'].get_journals_report(date_from=wizard.date_from, date_to=wizard.date_to, journal_ids=wizard.journal_ids.ids, posted_only=wizard.posted_only)
        return {'docs': wizard, 'data': report_data, 'date_from': wizard.date_from, 'date_to': wizard.date_to, 'generated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
