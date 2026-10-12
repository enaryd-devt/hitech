# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockAllocation(TransactionCase):
    def _create_external_destination(self, source, name="Destination"):
        parent = source.location_id.location_id or source.location_id
        return self.env["stock.location"].create({
            "name": name,
            "usage": "internal",
            "location_id": parent.id,
        })

    def test_allocation_excludes_destination(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 5)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({"request_id": request.id, "product_id": product.id, "product_uom_id": product.uom_id.id, "quantity_requested": 3})
        self.assertEqual(line.quantity_found, 5)
        self.assertEqual(line.allocation_ids.source_location_id, source)

    def test_onchange_allocation_commands_are_recomputed_on_create(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 5)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 3,
            "allocation_ids": [(0, 0, {
                "source_location_id": source.id,
                "quantity": 3,
            })],
        })
        self.assertEqual(len(line.allocation_ids), 1)
        self.assertEqual(line.allocation_ids.request_id, request)
        self.assertEqual(line.quantity_found, 5)

    def test_source_location_can_override_automatic_allocation_priority(self):
        source = self.env.ref("stock.stock_location_stock")
        alternate_source = self.env["stock.location"].create({
            "name": "Alternate Source",
            "usage": "internal",
            "location_id": source.location_id.id,
        })
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 5)
        self.env["stock.quant"]._update_available_quantity(product, alternate_source, 5)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 3,
            "source_location_id": alternate_source.id,
        })
        self.assertEqual(line.allocation_ids[:1].source_location_id, alternate_source)
        self.assertEqual(line.quantity_found, 5)

    def test_manual_source_location_change_is_preserved_and_recomputed(self):
        source = self.env.ref("stock.stock_location_stock")
        alternate_source = self.env["stock.location"].create({
            "name": "Alternate Source",
            "usage": "internal",
            "location_id": source.location_id.id,
        })
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 5)
        self.env["stock.quant"]._update_available_quantity(product, alternate_source, 7)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 3,
        })
        self.assertEqual(line.source_location_id, source)
        line.write({"source_location_id": alternate_source.id})
        self.assertEqual(line.source_location_id, alternate_source)
        self.assertEqual(line.allocation_ids[:1].source_location_id, alternate_source)
        self.assertEqual(line.quantity_found, 7)

    def test_source_location_is_proposed_automatically(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, source, 5)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 3,
        })
        self.assertEqual(line.source_location_id, source)

    def test_product_uom_is_not_manually_modifiable(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        dozen = self.env["uom.uom"].create({
            "name": "Test Dozen",
            "category_id": product.uom_id.category_id.id,
            "uom_type": "bigger",
            "factor_inv": 12,
        })
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": dozen.id,
            "quantity_requested": 3,
        })
        self.assertEqual(line.product_uom_id, product.uom_id)
        line.write({"product_uom_id": dozen.id})
        self.assertEqual(line.product_uom_id, product.uom_id)

    def test_packaging_columns_follow_product_packaging(self):
        source = self.env.ref("stock.stock_location_stock")
        destination = self._create_external_destination(source)
        product = self.env["product.product"].create({"name": "Packaged Product", "is_storable": True})
        Packaging = self.env["product.packaging"]
        packaging_vals = {"name": "Carton", "qty": 12}
        if "product_id" in Packaging._fields:
            packaging_vals["product_id"] = product.id
        if "product_tmpl_id" in Packaging._fields:
            packaging_vals["product_tmpl_id"] = product.product_tmpl_id.id
        packaging = Packaging.create(packaging_vals)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 24,
        })
        self.assertEqual(line.packaging_id, packaging)
        self.assertEqual(line.packaging_quantity, 2)

    def test_destination_warehouse_locations_are_excluded_from_allocations(self):
        destination_source = self.env.ref("stock.stock_location_stock")
        external_source = self.env["stock.location"].create({
            "name": "External Source",
            "usage": "internal",
            "location_id": destination_source.location_id.location_id.id,
        })
        destination = self.env["stock.location"].create({
            "name": "Destination",
            "usage": "internal",
            "location_id": destination_source.location_id.id,
        })
        product = self.env["product.product"].create({"name": "Allocated Product", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, destination_source, 5)
        self.env["stock.quant"]._update_available_quantity(product, external_source, 5)
        request = self.env["replenishment.request"].create({"destination_location_id": destination.id})
        line = self.env["replenishment.request.line"].create({
            "request_id": request.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "quantity_requested": 3,
        })
        self.assertEqual(line.allocation_ids.source_location_id, external_source)
