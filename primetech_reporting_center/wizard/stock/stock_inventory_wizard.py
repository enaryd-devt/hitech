# -*- coding: utf-8 -*-
from odoo import fields
from odoo import models

class StockInventoryWizard(models.TransientModel):
    _name = 'pt.stock.inventory.wizard'
    _description = 'PrimeTech Inventory Wizard'
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Entrepôts')
    location_ids = fields.Many2many('stock.location', string='Emplacements')
    category_ids = fields.Many2many('product.category', string='Catégories')
    product_ids = fields.Many2many('product.product', string='Produits')
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    group_by_supplier = fields.Boolean(string='Regrouper par fournisseur')
    lot_ids = fields.Many2many('stock.lot', string='Lots')
    only_out_of_stock = fields.Boolean(string='Produits en rupture')
    only_out_of_stock_lots = fields.Boolean(string='Lots en rupture')
    only_negative_stock = fields.Boolean(string='Stocks négatifs')
    only_with_lot = fields.Boolean(string='Produits avec lots')
    only_without_lot = fields.Boolean(string='Produits sans lots')
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {'company_id': self.company_id.id, 'warehouse_ids': self.warehouse_ids.ids, 'location_ids': self.location_ids.ids, 'category_ids': self.category_ids.ids, 'product_ids': self.product_ids.ids, 'supplier_ids': self.supplier_ids.ids, 'group_by_supplier': self.group_by_supplier, 'lot_ids': self.lot_ids.ids, 'only_out_of_stock': self.only_out_of_stock, 'only_out_of_stock_lots': self.only_out_of_stock_lots, 'only_negative_stock': self.only_negative_stock, 'only_with_lot': self.only_with_lot, 'only_without_lot': self.only_without_lot, 'observations': self.observations}

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['pt.stock.inventory'].get_report_data(self._prepare_filters())
        html = self.env['ir.qweb']._render('primetech_reporting_center.stock_inventory_preview_template', {'data': report_data, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Inventaire', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_stock_inventory_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_stock_inventory_xlsx', 'wizard_id': self.id, 'wizard_model': self._name})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu Inventaire', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_inventory_pdf').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_inventory_xlsx').report_action(self)

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_stock_dashboard'}
