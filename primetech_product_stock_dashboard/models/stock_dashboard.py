# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def get_primetech_stock_dashboard_data(self, filters=None):
        """Data for the stock overview. Operation cards are intentionally dynamic.

        A new warehouse or picking type automatically appears as a new card without
        any configuration in the dashboard.
        """
        filters = filters or {}
        companies = self.env.companies
        company_filter = filters.get("company_id")
        try:
            company_id = int(company_filter or 0)
        except (TypeError, ValueError):
            company_id = 0
        selected_company = companies.filtered(lambda company: company.id == company_id)[:1]
        if selected_company:
            self = self.with_company(selected_company).with_context(allowed_company_ids=[selected_company.id])
        else:
            self = self.with_context(allowed_company_ids=companies.ids)

        Warehouse = self.env["stock.warehouse"]
        warehouses = Warehouse.search([("company_id", "=", selected_company.id)] if selected_company else [], order="name")
        try:
            warehouse_id = int(filters.get("warehouse_id") or 0)
        except (TypeError, ValueError):
            warehouse_id = 0
        selected_warehouse = warehouses.filtered(lambda warehouse: warehouse.id == warehouse_id)[:1]
        warehouse_context = {"warehouse": selected_warehouse.id} if selected_warehouse else {}
        warehouse_domain = [("picking_type_id.warehouse_id", "=", selected_warehouse.id)] if selected_warehouse else []
        company_domain = [("company_id", "=", selected_company.id)] if selected_company else []

        Product = self.env["product.product"].with_context(active_test=True, **warehouse_context)
        # Only articles explicitly configured with inventory tracking belong
        # to the stock dashboard. Services and non-stocked consumables are
        # deliberately excluded from quantities and threshold alerts.
        products = Product.search([("is_storable", "=", True)])
        templates = products.mapped("product_tmpl_id")
        currency = self.env.company.currency_id
        available_qty = sum(products.mapped("qty_available"))
        stock_value = sum(product.qty_available * product.standard_price for product in products)
        critical = templates.filtered(lambda product: product.primetech_stock_level == "critical")
        warning = templates.filtered(lambda product: product.primetech_stock_level == "warning")
        healthy = templates.filtered(lambda product: product.primetech_stock_level == "healthy")

        Picking = self.env["stock.picking"]
        pending_domain = [("state", "not in", ("done", "cancel"))] + company_domain + warehouse_domain
        late_domain = pending_domain + [("scheduled_date", "<", fields.Datetime.now())]
        now = fields.Datetime.now()
        today = now.date()
        week_start = datetime.combine(today - timedelta(days=6), time.min)
        week_end = datetime.combine(today + timedelta(days=1), time.min)
        week_pickings = Picking.search(pending_domain + [
            ("scheduled_date", ">=", fields.Datetime.to_string(week_start)),
            ("scheduled_date", "<", fields.Datetime.to_string(week_end)),
        ])
        week_activity = defaultdict(lambda: defaultdict(lambda: {"on_time": 0, "late": 0}))
        for picking in week_pickings:
            if not picking.picking_type_id or not picking.scheduled_date:
                continue
            scheduled = fields.Datetime.to_datetime(picking.scheduled_date)
            bucket = week_activity[picking.picking_type_id.id][scheduled.date().isoformat()]
            bucket["late" if scheduled < now else "on_time"] += 1
        operation_cards = []
        operation_groups = {}
        picking_types = self.env["stock.picking.type"].search([("warehouse_id", "=", selected_warehouse.id)] if selected_warehouse else [], order="sequence, name")
        icons = {
            "incoming": "fa-sign-in", "outgoing": "fa-truck", "internal": "fa-exchange",
            "mrp_operation": "fa-cogs",
        }
        colors = {"incoming": "blue", "outgoing": "violet", "internal": "orange", "mrp_operation": "green"}
        for picking_type in picking_types:
            domain = pending_domain + [("picking_type_id", "=", picking_type.id)]
            late_count = Picking.search_count(late_domain + [("picking_type_id", "=", picking_type.id)])
            card = {
                "id": picking_type.id,
                "name": picking_type.name,
                "warehouse_name": picking_type.warehouse_id.display_name or "Sans entrepot",
                "code": picking_type.code,
                "icon": icons.get(picking_type.code, "fa-cube"),
                "color": colors.get(picking_type.code, "blue"),
                "pending": Picking.search_count(domain),
                "late": late_count,
                "days": [{
                    "label": (today - timedelta(days=offset)).strftime("%a")[:3].capitalize(),
                    "on_time": week_activity[picking_type.id][(today - timedelta(days=offset)).isoformat()]["on_time"],
                    "late": week_activity[picking_type.id][(today - timedelta(days=offset)).isoformat()]["late"],
                } for offset in range(6, -1, -1)],
                "action": "Voir les opérations",
            }
            operation_cards.append(card)
            warehouse = picking_type.warehouse_id
            group_key = warehouse.id or 0
            group = operation_groups.setdefault(group_key, {
                "id": warehouse.id or False,
                "name": warehouse.display_name if warehouse else "Operations without warehouse",
                "cards": [],
            })
            group["cards"].append(card)

        moves = self.env["stock.move"].search([
            ("state", "=", "done"), ("product_id.is_storable", "=", True),
        ] + company_domain + warehouse_domain, order="date desc, id desc", limit=8)
        recent_moves = [{
            "id": move.id,
            "date": fields.Datetime.to_string(move.date) if move.date else "",
            "name": move.reference or move.picking_id.name or "—",
            "product": move.product_id.display_name,
            "quantity": move.quantity,
            "operation": move.picking_type_id.name or "Mouvement",
            "state": "Réalisé",
            "type": move.picking_type_id.code or "internal",
        } for move in moves]

        shortages = templates.filtered(lambda product: product.qty_available > 0 and product.primetech_stock_level == "warning") | critical
        shortages = sorted(shortages, key=lambda product: (product.primetech_stock_level != "critical", product.qty_available))[:6]
        low_products = [{
            "id": product.id,
            "name": product.display_name,
            "reference": product.default_code or "",
            "available": product.qty_available,
            "alert": product.primetech_stock_alert_qty,
            "optimal": product.primetech_optimal_stock_qty,
            "image": "/web/image/product.template/%s/image_128" % product.id,
            "level": product.primetech_stock_level,
        } for product in shortages]

        category_quantities = defaultdict(float)
        category_alerts = defaultdict(int)
        category_names = {}
        for product in products:
            category = product.categ_id
            category_id = category.id or 0
            category_names[category_id] = category.display_name or "Sans catégorie"
            category_quantities[category_id] += product.qty_available
            if product.primetech_stock_level in ("warning", "critical"):
                category_alerts[category_id] += 1
        categories = sorted(category_quantities, key=category_quantities.get, reverse=True)[:6]
        # All categories can legitimately be at zero (or negative after stock
        # corrections).  A non-zero absolute scale keeps the dashboard usable
        # instead of failing while calculating the visual bar ratios.
        max_category_qty = max([abs(category_quantities[category]) for category in categories] or [1]) or 1
        category_data = [{
            "id": category,
            "name": category_names[category],
            "quantity": category_quantities[category],
            "ratio": round(abs(category_quantities[category]) / max_category_qty * 100, 2),
        } for category in categories]
        alert_categories = sorted(category_alerts, key=category_alerts.get, reverse=True)[:6]
        max_category_alerts = max([category_alerts[category] for category in alert_categories] or [1]) or 1
        alert_category_data = [{
            "id": category,
            "name": category_names[category],
            "count": category_alerts[category],
            "ratio": round(category_alerts[category] / max_category_alerts * 100, 2),
        } for category in alert_categories]

        incoming = Picking.search_count(pending_domain + [("picking_type_code", "=", "incoming")])
        outgoing = Picking.search_count(pending_domain + [("picking_type_code", "=", "outgoing")])
        late_count = Picking.search_count(late_domain)
        return {
            "currency": currency.symbol or currency.name,
            "currency_position": currency.position,
            "company_options": [{"id": company.id, "name": company.display_name} for company in companies],
            "warehouse_options": [{"id": warehouse.id, "name": warehouse.display_name} for warehouse in warehouses],
            "selected_company_id": selected_company.id if selected_company else "all",
            "selected_warehouse_id": selected_warehouse.id if selected_warehouse else "all",
            "kpis": [
                {"label": "Articles en stock", "value": len(templates), "detail": "Références actives", "icon": "fa-cube", "tone": "blue"},
                {"label": "À recevoir", "value": incoming, "detail": "Opérations en attente", "icon": "fa-download", "tone": "orange"},
                {"label": "À livrer", "value": outgoing, "detail": "Opérations en attente", "icon": "fa-truck", "tone": "violet"},
                {"label": "En retard", "value": late_count, "detail": "Opérations en retard", "icon": "fa-exclamation-triangle", "tone": "red"},
            ],
            "operations": operation_cards,
            "operation_groups": list(operation_groups.values()),
            "recent_moves": recent_moves,
            "low_products": low_products,
            "categories": category_data,
            "alert_categories": alert_category_data,
            "stock_levels": [
                {"label": "Stock satisfaisant", "value": len(healthy), "tone": "green"},
                {"label": "Stock faible", "value": len(warning), "tone": "orange"},
                {"label": "Rupture de stock", "value": len(critical), "tone": "red"},
            ],
        }
