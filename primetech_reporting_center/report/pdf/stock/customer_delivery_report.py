# -*- coding: utf-8 -*-
from odoo import api, models


class CustomerDeliveryPdfReport(models.AbstractModel):
    _name = 'report.primetech_reporting_center.customer_delivery_pdf'
    _description = 'PDF des produits déstockés et livrés'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard_model = self.env['pt.customer.delivery.wizard']
        wizard = wizard_model.browse(docids or self.env.context.get('active_ids') or self.env.context.get('active_id'))
        filters = (data or {}).get('filters')
        if wizard.exists():
            wizard = wizard.exists()[:1]
            filters = wizard._prepare_filters()
        else:
            # Odoo may call a report from the preview without docids.  The
            # preview forwards the filters, so rebuild a display-only wizard.
            filters = filters or {}
            wizard = wizard_model.new({
                'company_id': filters.get('company_id'),
                'date_from': filters.get('date_from'),
                'date_to': filters.get('date_to'),
                'warehouse_ids': [(6, 0, filters.get('warehouse_ids', []))],
                'category_ids': [(6, 0, filters.get('category_ids', []))],
                'product_ids': [(6, 0, filters.get('product_ids', []))],
                'customer_ids': [(6, 0, filters.get('customer_ids', []))],
            })
        return {'doc_ids': wizard.ids, 'doc_model': wizard._name, 'docs': wizard, 'wizard': wizard, 'data': self.env['pt.customer.delivery.report'].get_report_data(filters)}
