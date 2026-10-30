from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def get_product_info_pos(self, price, quantity, pos_config_id):
        """Expose the applied pricelist rule in the POS product assistant.

        The standard POS payload only returns a name and a computed amount.
        Returning the rule conditions makes the displayed price auditable by
        the cashier without granting access to the pricelist back-office.
        """
        self.ensure_one()
        info = super().get_product_info_pos(price, quantity, pos_config_id)
        config = self.env["pos.config"].browse(pos_config_id).exists()
        if not config:
            return info

        pricelists = (
            config.available_pricelist_ids
            if config.use_pricelist
            else config.pricelist_id
        )
        PricelistItem = self.env["product.pricelist.item"]
        # Do not reduce the result to the one rule currently applicable to
        # the selected quantity.  A cashier must be able to see every price
        # tier available for this article (for example 1, 10 and 50 units).
        price_rules = PricelistItem.search([
            ("pricelist_id", "in", pricelists.ids),
            "|", ("categ_id", "=", False), ("categ_id", "parent_of", self.categ_id.id),
            "|", ("product_tmpl_id", "=", False), ("product_tmpl_id", "=", self.product_tmpl_id.id),
            "|", ("product_id", "=", False), ("product_id", "=", self.id),
        ], order="pricelist_id, min_quantity, id")
        pricelist_rows = []
        for rule in price_rules:
            display_quantity = max(rule.min_quantity, 1.0)
            computed_price = rule._compute_price(
                self,
                display_quantity,
                self.uom_id,
                fields.Date.today(),
                currency=rule.pricelist_id.currency_id,
            )
            pricelist_rows.append({
                "id": rule.id,
                "name": rule.pricelist_id.name,
                "price": computed_price,
                "min_quantity": rule.min_quantity,
                "date_start": fields.Date.to_string(rule.date_start) if rule.date_start else False,
                "date_end": fields.Date.to_string(rule.date_end) if rule.date_end else False,
            })
        info["pricelists"] = pricelist_rows
        return info

    @api.model
    def _primetech_pos_stock_context(self, config_id):
        """Return the stock context of the POS operation type warehouse only."""
        config = self.env["pos.config"].browse(config_id).exists()
        warehouse = config.picking_type_id.warehouse_id
        # Never return an empty context here: an empty stock context makes
        # Odoo calculate qty_available over every warehouse.  A non-existing
        # warehouse deliberately yields zero instead, until the POS operation
        # type is correctly linked to an actual warehouse.
        return {"warehouse_id": warehouse.id or -1}

    def _load_pos_data_fields(self, config_id):
        """Expose the on-hand quantity to the POS product cards."""
        fields = super()._load_pos_data_fields(config_id)
        if "qty_available" not in fields:
            fields.append("qty_available")
        return fields

    @api.model
    def _load_product_with_domain(self, domain, config_id, load_archived=False):
        """Load the product quantity from this POS delivery warehouse.

        ``qty_available`` is a context-dependent product field.  Without the
        warehouse context, Odoo returns the total over every warehouse, which
        lets a cashier see stock that belongs to another POS.
        """
        fields = self._load_pos_data_fields(config_id)
        context = {
            **self.env.context,
            "display_default_code": False,
            "active_test": not load_archived,
            **self._primetech_pos_stock_context(config_id),
        }
        return self.with_context(context).search_read(
            domain,
            fields,
            order="sequence,default_code,name",
            load=False,
        )

    @api.model
    def primetech_pos_available_stock(self, product_id, config_id, order_id=False):
        """Physical stock less reservations from the other synchronized carts."""
        product = self.browse(product_id).exists()
        config = self.env["pos.config"].browse(config_id).exists()
        if not product or not config or not product.is_storable:
            return {"available_quantity": False, "reserved_quantity": 0.0}
        # Use precisely the same warehouse scope as the catalogue cards.
        # This prevents a cashier from using stock from another warehouse.
        stock = product.with_context(
            **self._primetech_pos_stock_context(config.id)
        ).qty_available
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

    @api.model
    def primetech_pos_reload_catalog(self, config_id):
        """Return the POS catalogue without reloading the whole POS session.

        ``pos.session.load_data`` also requires draft orders and their lines.
        Calling it only for products therefore fails during an open session.
        This lightweight endpoint uses exactly the POS product domain and can
        safely be called from the refresh button.
        """
        config = self.env["pos.config"].browse(config_id).exists()
        if not config:
            return []

        fields_to_load = self._load_pos_data_fields(config.id)
        if config.get_limited_product_count():
            products = config.with_context(display_default_code=False).get_limited_products_loading(
                fields_to_load
            )
        else:
            products = self._load_product_with_domain(
                config._get_available_product_domain(), config.id
            )
        self._process_pos_ui_product_product(products, config)
        return products
