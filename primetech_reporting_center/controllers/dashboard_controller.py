from odoo import http
from odoo.http import request
import json

class PrimetechDashboardController(http.Controller):

    @http.route('/primetech_reporting/dashboard/kpis', type='http', auth='user', csrf=False)
    def get_dashboard_kpis(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_dashboard_kpis(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/revenue_chart', type='http', auth='user', csrf=False)
    def revenue_chart(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_revenue_chart(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/activity_chart', type='http', auth='user', csrf=False)
    def activity_chart(self, **kwargs):
        import json
        data = request.env['primetech.dashboard'].sudo().get_activity_chart()
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_customers', type='http', auth='user', csrf=False)
    def top_customers(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_top_customers(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_products', type='http', auth='user', csrf=False)
    def top_products(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_top_products(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/unpaid_invoices', type='http', auth='user', csrf=False)
    def unpaid_invoices(self, **kwargs):
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_top_unpaid_invoices(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_reserved_products', type='http', auth='user', csrf=False)
    def top_reserved_products(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_top_reserved_products()
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/alerts', type='http', auth='user', csrf=False)
    def alerts(self, **kwargs):
        import json
        data = request.env['primetech.dashboard'].sudo().get_alerts()
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/receivables_chart', type='http', auth='user', csrf=False)
    def receivables_chart(self, **kwargs):
        data = request.env['primetech.dashboard'].sudo().get_receivables_chart()
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_salespersons', type='http', auth='user', csrf=False)
    def top_salespersons(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_top_salespersons(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/salespersons_chart', type='http', auth='user', csrf=False)
    def salespersons_chart(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_salespersons_chart(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/business_analysis', type='http', auth='user', csrf=False)
    def business_analysis(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_business_analysis(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/margin_analysis', type='http', auth='user', csrf=False)
    def margin_analysis(self, **kwargs):
        import json
        filters = {}
        try:
            filters = json.loads(request.httprequest.data or '{}')
        except Exception:
            pass
        data = request.env['primetech.dashboard'].sudo().get_margin_analysis(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_customers_chart', type='http', auth='user', csrf=False)
    def top_customers_chart(self, **kwargs):
        import json
        filters = json.loads(request.httprequest.data or '{}')
        data = request.env['primetech.dashboard'].sudo().get_top_customers_chart(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_products_chart', type='http', auth='user', csrf=False)
    def top_products_chart(self, **kwargs):
        import json
        filters = json.loads(request.httprequest.data or '{}')
        data = request.env['primetech.dashboard'].sudo().get_top_products_chart(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/top_salespersons_chart', type='http', auth='user', csrf=False)
    def top_salespersons_chart(self, **kwargs):
        import json
        filters = json.loads(request.httprequest.data or '{}')
        data = request.env['primetech.dashboard'].sudo().get_top_salespersons_chart(filters)
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/primetech_reporting/dashboard/champions', type='json', auth='user')
    def champions(self, **kwargs):
        return request.env['primetech.dashboard'].get_champions(kwargs)

    @http.route('/primetech_reporting/dashboard/targets_progress', type='json', auth='user')
    def targets_progress(self, **kwargs):
        return request.env['primetech.dashboard'].get_targets_progress(kwargs)

    @http.route('/primetech_reporting/dashboard/sales_forecast', type='json', auth='user')
    def sales_forecast(self, **kwargs):
        return request.env['primetech.dashboard'].get_sales_forecast(kwargs)

    @http.route('/primetech_reporting/dashboard/smart_alerts', type='json', auth='user')
    def smart_alerts(self, **kwargs):
        return request.env['primetech.dashboard'].get_smart_alerts()

    @http.route('/primetech_reporting/dashboard/finance_kpis', type='json', auth='user')
    def finance_kpis(self, **kwargs):
        return request.env['primetech.dashboard'].get_finance_kpis(kwargs)
