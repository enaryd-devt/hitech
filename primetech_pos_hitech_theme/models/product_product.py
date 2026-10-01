from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _load_pos_data_fields(self, config_id):
        """Expose the on-hand quantity to the POS product cards."""
        fields = super()._load_pos_data_fields(config_id)
        if "qty_available" not in fields:
            fields.append("qty_available")
        return fields

    @api.model
    def primetech_pos_available_stock(self, product_id, config_id, order_id=False):
        """Physical stock less reservations from the other synchronized carts."""
        product = self.browse(product_id).exists()
        config = self.env["pos.config"].browse(config_id).exists()
        if not product or not config or not product.is_storable:
            return {"available_quantity": False, "reserved_quantity": 0.0}
        # The POS card is fed with ``qty_available``.  Use the exact same
        # stock scope here, otherwise a global quantity displayed as 1 could
        # be rejected after the click because a different warehouse context
        # returned 0.
        stock = product.qty_available
        domain = [
            ("order_id.config_id", "=", config.id),
            ("order_id.state", "=", "draft"),
            ("product_id", "=", product.id),
        ]
        if order_id:
            domain.append(("order_id", "!=", int(order_id)))
        grouped = self.env["pos.order.line"]._read_group(domain, aggregates=["qty:sum"])
        reserved = grouped[0][0] if grouped else 0.0
        return {
            "available_quantity": max(0.0, stock - reserved),
            "reserved_quantity": reserved,
        }
