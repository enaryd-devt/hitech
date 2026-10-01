from odoo import api, fields, models

class PartnerBalanceReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.partner_balance_template'
    _description = 'Balance des Tiers PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.partner.balance.wizard'].browse(docids)
        report_data = self.env['primetech.partner.balance'].get_partner_balance(date_from=wizard.date_from, date_to=wizard.date_to, partner_type=wizard.partner_type, posted_only=wizard.posted_only)
        return {'docs': wizard, 'data': report_data, 'date_from': wizard.date_from, 'date_to': wizard.date_to, 'generated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
