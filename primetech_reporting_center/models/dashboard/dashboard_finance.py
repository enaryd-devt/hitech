from odoo import api, fields, models
from dateutil.relativedelta import relativedelta

class PrimetechDashboardFinance(models.AbstractModel):
    _inherit = 'primetech.dashboard'

    @api.model
    def get_business_analysis(self, filters=None):
        revenue = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]).mapped('amount_untaxed'))
        purchases = sum(self.env['purchase.order'].search([('state', 'in', ['purchase', 'done'])]).mapped('amount_untaxed'))
        receivables = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]).mapped('amount_residual'))
        reserved = self.env['stock.move'].search_count([('picking_id.picking_type_code', '=', 'outgoing'), ('state', 'in', ['assigned', 'partially_available'])])
        return {'labels': ['CA', 'Achats', 'Créances', 'Réservations'], 'values': [revenue, purchases, receivables, reserved]}

    @api.model
    def get_margin_analysis(self, filters=None):
        filters = filters or {}
        sale_domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]
        purchase_domain = [('state', 'in', ['purchase', 'done'])]
        sale_domain += self._get_date_domain(filters, 'invoice_date')
        purchase_domain += self._get_date_domain(filters, 'date_approve')
        revenue = sum(self.env['account.move'].search(sale_domain).mapped('amount_untaxed'))
        purchases = sum(self.env['purchase.order'].search(purchase_domain).mapped('amount_untaxed'))
        margin = revenue - purchases
        return {'labels': ['CA', 'Achats', 'Marge'], 'values': [revenue, purchases, margin]}
    _inherit = 'primetech.dashboard'

    @api.model
    def get_finance_kpis(self, filters=None):
        today = fields.Date.today()
        current_month_start = today.replace(day=1)
        previous_month_start = current_month_start - relativedelta(months=1)
        previous_month_end = current_month_start - relativedelta(days=1)
        revenue = self.env['sale.report'].search([])
        current_revenue = sum(revenue.filtered(lambda r: r.date >= current_month_start).mapped('price_total'))
        previous_revenue = sum(revenue.filtered(lambda r: previous_month_start <= r.date <= previous_month_end).mapped('price_total'))
        receivables = sum(self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]).mapped('amount_residual'))
        payables = sum(self.env['account.move'].search([('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]).mapped('amount_residual'))
        cash = sum(self.env['account.account'].search([('account_type', '=', 'asset_cash')]).mapped('current_balance'))
        revenue_variation = 0
        if previous_revenue:
            revenue_variation = (current_revenue - previous_revenue) / previous_revenue * 100
        return {'revenue': {'value': round(current_revenue), 'variation': round(revenue_variation, 1)}, 'receivables': {'value': round(receivables)}, 'payables': {'value': round(payables)}, 'cash': {'value': round(cash)}}
