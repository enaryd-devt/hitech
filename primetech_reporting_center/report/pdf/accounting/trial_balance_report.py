from datetime import datetime
from odoo import api, models

class TrialBalanceReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.trial_balance_report_template'
    _description = 'Trial Balance Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.trial.balance.wizard'].browse(docids[:1])
        wizard = self.env['primetech.trial.balance.wizard'].browse(docids[:1])
        previous_year = wizard.date_from.year - 1 if wizard.date_from else ''
        lines = self.env['primetech.trial.balance'].get_trial_balance(date_from=wizard.date_from, date_to=wizard.date_to, level=wizard.level, posted_only=wizard.posted_only)
        return {'docs': wizard, 'data': lines, 'date_from': wizard.date_from, 'date_to': wizard.date_to, 'previous_year': previous_year, 'generated_at': datetime.now().strftime('%d/%m/%Y %H:%M')}
