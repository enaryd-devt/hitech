# -*- coding: utf-8 -*-
from odoo import api
from odoo import models

class StockMovementPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.stock_movement_pdf'
    _description = 'PrimeTech Stock Movement PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['pt.stock.movement.wizard'].browse(docids)
        if not wizard:
            wizard = self.env['pt.stock.movement.wizard'].browse(self.env.context.get('active_id'))
        report_data = self.env['pt.stock.movement'].get_report_data(wizard._prepare_filters())
        return {'doc_ids': wizard.ids, 'doc_model': wizard._name, 'docs': wizard, 'wizard': wizard, 'data': report_data}
