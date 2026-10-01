# -*- coding: utf-8 -*-
from odoo import fields, models

class ReportPurchasePreviewWizard(models.TransientModel):
    _name = 'primetech.purchase.preview.wizard'
    _description = 'Prévisualisation Rapport Achat'
    name = fields.Char(string='Nom du Rapport')
    html = fields.Html(string='Aperçu', sanitize=False, readonly=True)
    pdf_report_ref = fields.Char()
    xlsx_report_ref = fields.Char()
    wizard_id = fields.Integer()
    wizard_model = fields.Char()

    def action_print_pdf(self):
        self.ensure_one()
        if not self.pdf_report_ref:
            return False
        wizard = self.env[self.wizard_model].browse(self.wizard_id)
        if not wizard.exists():
            return False
        return self.env.ref(self.pdf_report_ref).report_action(wizard, data={'filters': wizard._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.xlsx_report_ref:
            return False
        wizard = self.env[self.wizard_model].browse(self.wizard_id)
        if not wizard.exists():
            return False
        return self.env.ref(self.xlsx_report_ref).report_action(wizard, data={'filters': wizard._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'purchase_overview_dashboard'}
