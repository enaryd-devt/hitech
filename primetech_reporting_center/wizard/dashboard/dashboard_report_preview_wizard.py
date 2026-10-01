# -*- coding: utf-8 -*-
import json

from odoo import fields, models


class DashboardReportPreviewWizard(models.TransientModel):
    _name = 'pt.dashboard.report.preview.wizard'
    _description = 'Prévisualisation des rapports du tableau de bord'

    name = fields.Char(string='Rapport', readonly=True)
    html_content = fields.Html(string='Aperçu', sanitize=False, readonly=True)
    report_xmlid = fields.Char(string='Rapport PDF', readonly=True)
    report_payload = fields.Text(string='Paramètres du rapport', readonly=True)

    def action_print_pdf(self):
        self.ensure_one()
        if not self.report_xmlid:
            return False
        try:
            payload = json.loads(self.report_payload or '{}')
        except (TypeError, ValueError):
            payload = {}
        return self.env.ref(self.report_xmlid).report_action(
            self.env.company, data=payload
        )

    def action_back(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'primetech_reporting_dashboard',
        }
