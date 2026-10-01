from odoo import fields, models

class BalanceSheetReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.balance_sheet_template'
    _description = 'Bilan OHADA Report'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['primetech.balance.sheet.wizard'].browse(docids[:1])
        date_to = wizard.date_to
        posted_only = wizard.posted_only
        if data:
            date_to = data.get('date_to', date_to)
            posted_only = data.get('posted_only', posted_only)
            display_mode = 'both'
            if data:
                display_mode = data.get('display_mode', 'both')
        report_data = self.env['primetech.balance.sheet'].get_balance_sheet(date_to=date_to, posted_only=posted_only)
        return {'docs': wizard, 'data': report_data, 'display_mode': display_mode, 'date_to': date_to, 'generated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
