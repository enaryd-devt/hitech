# -*- coding: utf-8 -*-
from odoo import fields, models


class CustomerDeliveryWizard(models.TransientModel):
    _name = 'pt.customer.delivery.wizard'
    _description = 'Rapport des produits déstockés et livrés'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Du', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Au', required=True, default=fields.Date.today)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Entrepôts')
    category_ids = fields.Many2many('product.category', string='Catégories')
    product_ids = fields.Many2many('product.product', string='Produits')
    customer_ids = fields.Many2many('res.partner', string='Clients', domain=[('customer_rank', '>', 0)])
    observations = fields.Text(string='Observations')

    def _prepare_filters(self):
        self.ensure_one()
        return {
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'warehouse_ids': self.warehouse_ids.ids,
            'category_ids': self.category_ids.ids,
            'product_ids': self.product_ids.ids,
            'customer_ids': self.customer_ids.ids,
        }

    def action_preview(self):
        self.ensure_one()
        report_data = self.env['pt.customer.delivery.report'].get_report_data(self._prepare_filters())
        html = self.env['ir.qweb']._render(
            'primetech_reporting_center.customer_delivery_preview_template',
            {'data': report_data, 'wizard': self},
        )
        preview = self.env['primetech.purchase.preview.wizard'].create({
            'name': 'Produits déstockés / livrés',
            'html': html,
            'pdf_report_ref': 'primetech_reporting_center.action_customer_delivery_pdf',
            'xlsx_report_ref': 'primetech_reporting_center.action_customer_delivery_xlsx',
            'wizard_id': self.id,
            'wizard_model': self._name,
        })
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu des livraisons', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        return self.env.ref('primetech_reporting_center.action_customer_delivery_pdf').report_action(self)

    def action_export_xlsx(self):
        return self.env.ref('primetech_reporting_center.action_customer_delivery_xlsx').report_action(self)
