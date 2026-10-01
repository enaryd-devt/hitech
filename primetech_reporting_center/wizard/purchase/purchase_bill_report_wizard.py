# -*- coding: utf-8 -*-
from odoo import fields, models

class PurchaseBillReportWizard(models.TransientModel):
    _name = 'pt.purchase.bill.wiz'
    _description = 'Purchase Vendor Bills Report Wizard'
    date_from = fields.Date(string='Date début', required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Date fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    supplier_ids = fields.Many2many('res.partner', string='Fournisseurs', domain=[('supplier_rank', '>', 0)])
    payment_state = fields.Selection([('all', 'Tous'), ('not_paid', 'Non payé'), ('in_payment', 'En paiement'), ('partial', 'Partiellement payé'), ('paid', 'Payé'), ('reversed', 'Extourné')], string='Statut de paiement', default='all', required=True)

    def _prepare_filters(self):
        self.ensure_one()
        return {'date_from': self.date_from, 'date_to': self.date_to, 'company_id': self.company_id.id, 'supplier_ids': self.supplier_ids.ids, 'payment_state': self.payment_state}

    def action_preview(self):
        self.ensure_one()
        filters = self._prepare_filters()
        report_data = self.env['pt.purchase.bill'].get_report_data(filters)
        html = self.env['ir.qweb']._render('primetech_reporting_center.purchase_bill_preview_template', {'data': report_data, 'filters': filters, 'wizard': self})
        preview = self.env['primetech.purchase.preview.wizard'].create({'name': 'Factures Fournisseurs', 'html': html, 'pdf_report_ref': 'primetech_reporting_center.action_purchase_bill_pdf', 'xlsx_report_ref': 'primetech_reporting_center.action_purchase_bill_xlsx', 'wizard_id': self.id, 'wizard_model': 'pt.purchase.bill.wiz'})
        return {'type': 'ir.actions.act_window', 'name': 'Aperçu', 'res_model': 'primetech.purchase.preview.wizard', 'view_mode': 'form', 'target': 'current', 'res_id': preview.id}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_purchase_bill_pdf').report_action(self, data={'filters': self._prepare_filters()})

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref('primetech_reporting_center.action_purchase_bill_xlsx').report_action(self, data={'filters': self._prepare_filters()})

    def action_back(self):
        return {'type': 'ir.actions.client', 'tag': 'primetech_purchase_overview_dashboard'}
