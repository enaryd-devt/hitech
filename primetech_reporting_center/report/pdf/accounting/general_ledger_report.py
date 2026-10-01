from odoo import api, fields, models
import json

class GeneralLedgerReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.gl_report_template'
    _description = 'Grand Livre Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard = self.env['primetech.general.ledger.wizard'].browse(docids)
        if data.get('preview_data'):
            ledger_data = json.loads(data['preview_data'])
        else:
            ledger_data = self.env['primetech.general.ledger'].get_general_ledger(date_from=wizard.date_from, date_to=wizard.date_to, account_from=wizard.account_from_id.code if wizard.account_from_id else False, account_to=wizard.account_to_id.code if wizard.account_to_id else False, posted_only=wizard.posted_only, hide_zero_balance=wizard.hide_zero_balance)
        return {'docs': wizard, 'data': ledger_data, 'date_from': wizard.date_from, 'date_to': wizard.date_to, 'generated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
