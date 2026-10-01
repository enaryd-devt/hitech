# -*- coding: utf-8 -*-
from odoo import fields
from odoo import models

class StockMovementWizard(models.TransientModel):
    _name = 'pt.stock.movement.wizard'
    _description = 'PrimeTech Stock Movement Wizard'
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Date début', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Entrepôts')
    category_ids = fields.Many2many('product.category', string='Catégories')
    product_ids = fields.Many2many('product.product', string='Produits')
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    group_by_supplier = fields.Boolean(string='Regrouper par fournisseur')
    lot_ids = fields.Many2many('stock.lot', string='Lots')
    show_cost = fields.Boolean(string='Afficher les coûts', default=True)
    show_valuation = fields.Boolean(string='Afficher la valorisation', default=True)
    validated_only = fields.Boolean(string='Mouvements validés uniquement', default=True)
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {'company_id': self.company_id.id, 'date_from': self.date_from, 'date_to': self.date_to, 'warehouse_ids': self.warehouse_ids.ids, 'category_ids': self.category_ids.ids, 'product_ids': self.product_ids.ids, 'supplier_ids': self.supplier_ids.ids, 'group_by_supplier': self.group_by_supplier, 'lot_ids': self.lot_ids.ids, 'show_cost': self.show_cost, 'show_valuation': self.show_valuation, 'validated_only': self.validated_only, 'observations': self.observations}

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['pt.stock.movement'].get_report_data(self._prepare_filters())
        html = self.env['ir.qweb']._render('primetech_reporting_center.stock_movement_preview_template', {'data': report_data, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Mouvements de Stock', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_stock_movement_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_stock_movement_xlsx', 'wizard_id': self.id, 'wizard_model': self._name})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_movement_pdf').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_stock_movement_xlsx').report_action(self)

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_stock_dashboard'}
