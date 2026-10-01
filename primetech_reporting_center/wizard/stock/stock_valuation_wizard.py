# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import fields
from odoo import models

class StockValuationWizard(models.TransientModel):
    _name = 'pt.stock.valuation.wizard'
    _description = 'PrimeTech Stock Valuation Wizard'
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Entrepôts')
    location_ids = fields.Many2many('stock.location', string='Emplacements')
    category_ids = fields.Many2many('product.category', string='Catégories')
    product_ids = fields.Many2many('product.product', string='Produits')
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    group_by_supplier = fields.Boolean(string='Regrouper par fournisseur')
    only_available = fields.Boolean(string='Stock positif uniquement')
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {'company_id': self.company_id.id, 'warehouse_ids': self.warehouse_ids.ids, 'location_ids': self.location_ids.ids, 'category_ids': self.category_ids.ids, 'product_ids': self.product_ids.ids, 'supplier_ids': self.supplier_ids.ids, 'group_by_supplier': self.group_by_supplier, 'only_available': self.only_available, 'observations': self.observations}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        report_data = self.env['pt.stock.valuation'].get_report_data(filters)
        html = self.env['ir.qweb']._render('primetech_reporting_center.stock_valuation_preview_template', {'data': report_data, 'filters': filters, 'wizard': self, 'generated_at': datetime.now().strftime('%d/%m/%Y %H:%M')})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Valorisation du Stock', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_stock_valuation_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_stock_valuation_xlsx', 'wizard_id': self.id, 'wizard_model': 'pt.stock.valuation.wizard'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_valuation_pdf').report_action(self, data={'filters': self._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_valuation_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_stock_dashboard'}
