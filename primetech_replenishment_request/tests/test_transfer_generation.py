# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTransferGeneration(TransactionCase):
    def test_approve_creates_done_picking(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self.env["stock.location"].create({"name": "Transfer Destination", "usage": "internal", "location_id": source.location_id.id})
        product = self.env["product.product"].create({"name": "Transferred Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 2)
        request = self.env["replenishment.request"].create({
            "destination_location_id": destination.id,
            "line_ids": [(0, 0, {"product_id": product.id, "product_uom_id": product.uom_id.id, "quantity_requested": 2})],
        })
        request.action_submit()
        request.action_approve()
        self.assertEqual(request.state, "approved")
        self.assertTrue(request.picking_ids)
        self.assertEqual(set(request.picking_ids.mapped("state")), {"done"})

    def test_transfer_cost_creates_stock_valuation_layers_by_quantity(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self.env["stock.location"].create({"name": "Cost Destination", "usage": "internal", "location_id": source.location_id.id})
        product_a = self.env["product.product"].create({"name": "Cost Product A", "is_storable": True})
        product_b = self.env["product.product"].create({"name": "Cost Product B", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product_a, source, 2)
        self.env["stock.quant"]._update_available_quantity(product_b, source, 3)
        request = self.env["replenishment.request"].create({
            "destination_location_id": destination.id,
            "define_transfer_cost": True,
            "transfer_cost_amount": 100.0,
            "transfer_cost_allocation_method": "quantity",
            "line_ids": [
                (0, 0, {"product_id": product_a.id, "product_uom_id": product_a.uom_id.id, "quantity_requested": 2}),
                (0, 0, {"product_id": product_b.id, "product_uom_id": product_b.uom_id.id, "quantity_requested": 3}),
            ],
        })
        request.action_submit()
        request.action_approve()

        valuation_layers = request.transfer_cost_valuation_layer_ids
        self.assertEqual(len(valuation_layers), 2)
        self.assertEqual(sum(valuation_layers.mapped("value")), 100.0)
        self.assertEqual(valuation_layers.filtered(lambda layer: layer.product_id == product_a).value, 40.0)
        self.assertEqual(valuation_layers.filtered(lambda layer: layer.product_id == product_b).value, 60.0)
