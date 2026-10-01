from odoo import api, fields, models

class PrimetechDashboardAlerts(models.AbstractModel):
    _inherit = 'primetech.dashboard'

    @api.model
    def get_smart_alerts(self):
        alerts = []
        overdue_invoices = self.env['account.move'].search_count([('move_type', '=', 'out_invoice'), ('payment_state', 'not in', ['paid', 'in_payment']), ('invoice_date_due', '!=', False), ('invoice_date_due', '<', fields.Date.today())])
        if overdue_invoices:
            alerts.append({'type': 'danger', 'icon': '🔴', 'message': f'{overdue_invoices} factures échues', 'action': 'overdue_invoices'})
        low_stock = self.env['product.product'].search_count([('qty_available', '<=', 5), ('qty_available', '>', 0)])
        if low_stock:
            alerts.append({'type': 'warning', 'icon': '🟠', 'message': f'{low_stock} produits en stock critique', 'action': 'low_stock'})
        out_of_stock = self.env['product.product'].search_count([('qty_available', '<=', 0)])
        if out_of_stock:
            alerts.append({'type': 'danger', 'icon': '⛔', 'message': f'{out_of_stock} produits en rupture', 'action': 'out_of_stock'})
        return alerts
