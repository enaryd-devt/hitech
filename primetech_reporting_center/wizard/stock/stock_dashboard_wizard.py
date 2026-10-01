# -*- coding: utf-8 -*-
from odoo import models

class StockDashboardWizard(models.TransientModel):
    _name = 'pt.stock.dashboard.wizard'
    _description = 'Stock Dashboard Wizard'

    def action_open_dashboard(self):
        dashboard = self.env['pt.stock.dashboard']
        data = dashboard.get_dashboard_data()
        html = self.env['ir.qweb']._render('primetech_reporting_center.stock_dashboard_template', {'data': data})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': "Vue d'Ensemble Stock", 'html': html})
        return {'type': 'ir.actions.act_window', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}
