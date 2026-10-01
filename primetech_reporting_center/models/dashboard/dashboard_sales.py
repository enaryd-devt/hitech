from odoo import api, models
from datetime import date
import calendar
import logging
_logger = logging.getLogger(__name__)

class PrimetechDashboardSales(models.AbstractModel):
    _inherit = 'primetech.dashboard'

    @api.model
    def get_top_salespersons(self, filters=None, limit=10):
        filters = filters or {}
        domain = []
        domain += self._get_date_domain(filters, 'date')
        salespersons = self.env['sale.report'].read_group(domain, ['user_id', 'price_total:sum'], ['user_id'], lazy=False)
        result = []
        for salesperson in salespersons:
            user = salesperson.get('user_id')
            if not user:
                continue
            result.append({'id': user[0], 'name': user[1], 'amount': float(salesperson.get('price_total', 0)), 'orders': int(salesperson.get('__count', 0))})
        result.sort(key=lambda x: x['amount'], reverse=True)
        return result[:limit]

    @api.model
    def get_top_salespersons_chart(self, filters=None):
        salespersons = self.get_top_salespersons(filters=filters, limit=10)
        return {'labels': [salesperson['name'] for salesperson in salespersons], 'values': [salesperson['amount'] for salesperson in salespersons], 'orders': [salesperson['orders'] for salesperson in salespersons]}

    @api.model
    def get_top_customers_chart(self, filters=None):
        customers = self.get_top_customers(filters, limit=10)
        return {'labels': [customer['name'] for customer in customers], 'values': [customer['amount'] for customer in customers]}

    @api.model
    def get_top_products_chart(self, filters=None):
        products = self.get_top_products(filters)
        return {'labels': [product['name'] for product in products[:10]], 'values': [product['amount'] for product in products[:10]]}

    @api.model
    def get_top_salespersons_chart(self, filters=None):
        try:
            salespersons = self.get_top_salespersons(filters=filters, limit=10)
            return {'labels': [salesperson.get('name', 'Sans commercial') for salesperson in salespersons], 'values': [float(salesperson.get('amount', 0)) for salesperson in salespersons], 'orders': [int(salesperson.get('orders', 0)) for salesperson in salespersons]}
        except Exception as e:
            _logger.exception('Erreur get_top_salespersons_chart')
            return {'labels': [], 'values': [], 'orders': []}

    @api.model
    def get_top_customers(self, filters=None, limit=10):
        filters = filters or {}
        domain = []
        domain += self._get_date_domain(filters, 'date')
        customers = self.env['sale.report'].read_group(domain, ['partner_id', 'price_total:sum'], ['partner_id'], lazy=False)
        result = []
        for customer in customers:
            if not customer.get('partner_id'):
                continue
            result.append({'id': customer['partner_id'][0], 'name': customer['partner_id'][1], 'amount': customer.get('price_total', 0), 'count': customer.get('__count', 0)})
        result.sort(key=lambda x: x['amount'], reverse=True)
        return result[:limit]

    @api.model
    def get_top_products(self, filters=None, limit=10):
        filters = filters or {}
        domain = []
        domain += self._get_date_domain(filters, 'date')
        products = self.env['sale.report'].read_group(domain, ['product_id', 'price_total:sum', 'product_uom_qty:sum'], ['product_id'], lazy=False)
        result = []
        for product in products:
            if not product['product_id']:
                continue
            result.append({'id': product['product_id'][0], 'name': product['product_id'][1], 'amount': product['price_total'], 'qty': int(product['product_uom_qty'])})
        return sorted(result, key=lambda x: x['amount'], reverse=True)[:limit]

    @api.model
    def get_champions(self, filters=None):
        customers = self.get_top_customers(filters=filters, limit=1)
        products = self.get_top_products(filters=filters, limit=1)
        salespersons = self.get_top_salespersons(filters=filters, limit=1)
        customer = customers[0] if customers else {}
        product = products[0] if products else {}
        salesperson = salespersons[0] if salespersons else {}
        _logger.warning('CHAMPIONS => %s', {'customer': customer, 'product': product, 'salesperson': salesperson})
        return {'customer': customer, 'product': product, 'salesperson': salesperson}

    @api.model
    def get_targets_progress(self, filters=None):
        filters = filters or {}
        domain = self._get_date_domain(filters, 'date')
        sales = self.env['sale.report'].search(domain)
        revenue = sum(sales.mapped('price_total'))
        orders = len(sales)
        customers = len(set(sales.mapped('partner_id.id')))
        targets = {'revenue': 100000000, 'orders': 500, 'customers': 100}
        return {'revenue': {'actual': revenue, 'target': targets['revenue'], 'percent': min(round(revenue / targets['revenue'] * 100, 1), 100) if targets['revenue'] else 0}, 'orders': {'actual': orders, 'target': targets['orders'], 'percent': min(round(orders / targets['orders'] * 100, 1), 100) if targets['orders'] else 0}, 'customers': {'actual': customers, 'target': targets['customers'], 'percent': min(round(customers / targets['customers'] * 100, 1), 100) if targets['customers'] else 0}}

    @api.model
    def get_sales_forecast(self, filters=None):
        today = date.today()
        first_day = today.replace(day=1)
        days_elapsed = today.day
        total_days = calendar.monthrange(today.year, today.month)[1]
        domain = [('date', '>=', first_day), ('date', '<=', today)]
        sales = self.env['sale.report'].search(domain)
        revenue = sum(sales.mapped('price_total'))
        projection = 0
        if days_elapsed:
            projection = revenue / days_elapsed * total_days
        target = 75000000
        achievement = 0
        if target:
            achievement = round(projection / target * 100, 1)
        return {'actual': revenue, 'projection': projection, 'target': target, 'achievement': achievement}
