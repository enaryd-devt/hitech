from odoo import fields, models

class VATReportPDF(models.AbstractModel):
    _name = 'report.primetech_reporting_center.vat_report_template'
    _description = 'Rapport TVA PDF'

    def _get_report_values(self, docids, data=None):
        report_data = self.env['primetech.vat.report'].get_report_data(date_from=data.get('date_from'), date_to=data.get('date_to'), posted_only=data.get('posted_only'))
        return {'data': report_data, 'date_from': data.get('date_from'), 'date_to': data.get('date_to'), 'generated_at': fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
