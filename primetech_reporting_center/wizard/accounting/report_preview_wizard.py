from odoo import fields, models

class ReportPreviewWizard(models.TransientModel):
    _name = 'primetech.report.preview.wizard'
    _description = 'Prévisualisation Rapport'
    name = fields.Char(string='Titre', readonly=True)
    html_content = fields.Html(string='Aperçu', sanitize=False, readonly=True)
    report_xmlid = fields.Char(string='Rapport', readonly=True)
    wizard_id = fields.Integer(string='Wizard Source', readonly=True)

    def action_print(self):
        self.ensure_one()
        if not self.report_xmlid:
            return False
        wizard = self.env['primetech.general.ledger.wizard'].browse(self.wizard_id)
        return self.env.ref(self.report_xmlid).report_action(wizard)

    def action_export_pdf(self):
        return self.action_print()

    def action_back_to_menu(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_accounting_dashboard'}
