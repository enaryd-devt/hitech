# -*- coding: utf-8 -*-
from odoo import fields, models

class PurchaseSupplierPerformanceReportWizard(models.TransientModel):
    _name = 'pt.purchase.supp.wiz'
    _description = 'Purchase Supplier Performance Report Wizard'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    state = fields.Selection([('all', 'Tous'), ('draft', 'Brouillon'), ('sent', 'RFQ Envoyée'), ('to approve', 'À approuver'), ('purchase', 'Commande'), ('done', 'Verrouillée'), ('cancel', 'Annulée')], string='Statut', default='all', required=True)

    def _prepare_filters(self):
        self.ensure_one()
        return {'date_from': self.date_from, 'date_to': self.date_to, 'company_id': self.company_id.id, 'supplier_ids': self.supplier_ids.ids, 'state': self.state}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        report_data = self.env['pt.purchase.supp'].get_report_data(filters)
        html = self.env['ir.qweb']._render('primetech_reporting_center.purchase_supplier_perf_preview_template', {'data': report_data, 'filters': filters, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Performance Fournisseurs', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_purchase_supplier_perf_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_purchase_supplier_perf_xlsx', 'wizard_id': self.id, 'wizard_model': 'pt.purchase.supp.wiz'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_purchase_supplier_perf_pdf').report_action(self, data={'filters': self._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_purchase_supplier_perf_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_purchase_overview_dashboard'}
