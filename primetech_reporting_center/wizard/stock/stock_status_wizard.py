# -*- coding: utf-8 -*-
from odoo import fields
from odoo import models

class StockStatusWizard(models.TransientModel):
    _name = 'pt.stock.status.wizard'
    _description = 'Stock Status Report Wizard'
    date_from = fields.Date(string='Date début', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Entrepôts')
    location_ids = fields.Many2many('stock.location', string='Emplacements')
    category_ids = fields.Many2many('product.category', string='Catégories')
    product_ids = fields.Many2many('product.product', string='Produits')
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    group_by_supplier = fields.Boolean(string='Regrouper par fournisseur')
    lot_ids = fields.Many2many('stock.lot', string='Lots / Séries')
    only_available = fields.Boolean(string='Stock disponible > 0')
    only_out_of_stock = fields.Boolean(string='Ruptures uniquement')
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {'date_from': self.date_from, 'date_to': self.date_to, 'company_id': self.company_id.id, 'warehouse_ids': self.warehouse_ids.ids, 'location_ids': self.location_ids.ids, 'category_ids': self.category_ids.ids, 'product_ids': self.product_ids.ids, 'supplier_ids': self.supplier_ids.ids, 'group_by_supplier': self.group_by_supplier, 'lot_ids': self.lot_ids.ids, 'only_available': self.only_available, 'only_out_of_stock': self.only_out_of_stock, 'observations': self.observations}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        report_data = self.env['pt.stock.status'].get_report_data(filters)
        from datetime import datetime
        html = self.env['ir.qweb']._render('primetech_reporting_center.stock_status_preview_template', {'data': report_data, 'filters': filters, 'wizard': self, 'generated_at': datetime.now().strftime('%d/%m/%Y %H:%M')})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Etat de Stock', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_stock_status_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_stock_status_xlsx', 'wizard_id': self.id, 'wizard_model': 'pt.stock.status.wizard'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_status_pdf').report_action(self, data={'filters': self._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_status_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_stock_dashboard'}
