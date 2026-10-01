# -*- coding: utf-8 -*-
from odoo import fields, models

class PrimetechPurchaseProductReportWizard(models.TransientModel):
    _name = 'primetech.purchase.product.report.wizard'
    _description = 'Purchase Product Report Wizard'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    state = fields.Selection([('all', 'Tous'), ('draft', 'Brouillon'), ('sent', 'Envoyé'), ('purchase', 'Confirmé'), ('done', 'Terminé'), ('cancel', 'Annulé')], string='Statut', default='all', required=True)

    def _prepare_filters(self):
        self.ensure_one()
        return {'date_from': self.date_from, 'date_to': self.date_to, 'company_id': self.company_id.id, 'supplier_ids': self.supplier_ids.ids, 'state': self.state}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        report_data = self.env['primetech.purchase.product.report'].get_report_data(filters)
        html = self.env['ir.qweb']._render('primetech_reporting_center.purchase_product_preview', {'data': report_data, 'filters': filters, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Achats par Produit', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.purchase_product_pdf_report', 'xlsx_report_ref': 'primetech_reporting_center.purchase_product_xlsx', 'wizard_id': self.id, 'wizard_model': 'primetech.purchase.product.report.wizard'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.purchase_product_pdf_report').report_action(self, data={'filters': self._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.purchase_product_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_purchase_overview_dashboard'}
