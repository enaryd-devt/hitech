# -*- coding: utf-8 -*-
from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _get_replenishment_candidates(self, product, destination_location):
        """Return usable internal quants, excluding the selected destination warehouse."""
        excluded_locations = destination_location
        warehouse = self.env["stock.warehouse"].search([]).filtered(
            lambda wh: destination_location.id in wh.view_location_id.child_internal_location_ids.ids
        )[:1]
        if warehouse:
            excluded_locations = warehouse.view_location_id.child_internal_location_ids
        domain = [
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
            ("location_id", "not in", excluded_locations.ids),
            ("quantity", ">", 0),
        ]
        quants = self.search(domain, order="location_id, in_date, id")
        return quants.filtered(lambda quant: quant.available_quantity > 0)
