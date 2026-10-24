# -*- coding: utf-8 -*-
from odoo import models


class PrimetechPosSessionSalesReport(models.AbstractModel):
    """Adds the remaining POS warehouse stock to the standard session report."""

    _inherit = "report.point_of_sale.report_saledetails"

    def _primetech_report_warehouse(self, session_ids, config_ids):
        """Return the source warehouse used by the POS session/report."""
        sessions = self.env["pos.session"].browse(session_ids or []).exists()
        config = sessions[:1].config_id
        if not config and config_ids:
            config = self.env["pos.config"].browse(config_ids[:1]).exists()
        if not config:
            return self.env["stock.warehouse"]
        return config.warehouse_id or config.picking_type_id.warehouse_id

    def _primetech_add_remaining_stock(self, categories, warehouse):
        """The quantity is read in the POS destocking warehouse at print time."""
        if not warehouse:
            return
        product_ids = {
            line["product_id"]
            for category in categories
            for line in category.get("products", [])
            if line.get("product_id")
        }
        products = self.env["product.product"].browse(list(product_ids)).exists()
        quantities = {
            product.id: product.with_context(warehouse_id=warehouse.id).qty_available
            for product in products
        }
        for category in categories:
            for line in category.get("products", []):
                line["primetech_stock_remaining"] = quantities.get(line.get("product_id"), 0.0)

    def _primetech_session_people(self, session_ids):
        """Prepare the POS, cashier and sellers shown in the report heading."""
        session = self.env["pos.session"].browse(session_ids or []).exists()[:1]
        if not session:
            return {
                "primetech_pos_name": "",
                "primetech_cashier_name": "",
                "primetech_seller_names": [],
            }

        orders = self.env["pos.order"].search([("session_id", "=", session.id)])
        sellers = []
        for order in orders:
            seller = order.employee_id.name or order.user_id.name
            if seller and seller not in sellers:
                sellers.append(seller)
        cashier = session.employee_id.name or session.user_id.name or ""
        return {
            "primetech_pos_name": session.config_id.name or "",
            "primetech_cashier_name": cashier,
            "primetech_seller_names": sellers,
        }

    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False,
                         session_ids=False, **kwargs):
        result = super().get_sale_details(
            date_start=date_start,
            date_stop=date_stop,
            config_ids=config_ids,
            session_ids=session_ids,
            **kwargs,
        )
        warehouse = self._primetech_report_warehouse(session_ids, config_ids)
        self._primetech_add_remaining_stock(result.get("products", []), warehouse)
        self._primetech_add_remaining_stock(result.get("refund_products", []), warehouse)
        result["primetech_pos_warehouse_name"] = warehouse.name or ""
        result.update(self._primetech_session_people(session_ids))
        return result
