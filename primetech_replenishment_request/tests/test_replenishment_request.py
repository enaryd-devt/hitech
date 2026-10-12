# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReplenishmentRequest(TransactionCase):
    def _create_request(self):
        location = self.env.ref("stock.stock_location_stock")
        product = self.env["product.product"].create({"name": "Test Product", "is_storable": True})
        return self.env["replenishment.request"].create({
            "destination_location_id": location.id,
            "line_ids": [(0, 0, {"product_id": product.id, "product_uom_id": product.uom_id.id, "quantity_requested": 1})],
        })

    def test_create_submit_cancel(self):
        request = self._create_request()
        self.assertEqual(request.state, "draft")
        request.action_submit()
        self.assertEqual(request.state, "to_approve")
        request.action_cancel()
        self.assertEqual(request.state, "cancelled")

    def test_only_manager_can_reset_to_draft(self):
        request = self._create_request()
        request.action_submit()
        user = self.env["res.users"].create({
            "name": "Replenishment user",
            "login": "replenishment-reset-user",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        request.requester_id = user
        with self.assertRaises(AccessError):
            request.with_user(user).action_reset_to_draft()

        manager_group = self.env.ref(
            "primetech_replenishment_request.group_replenishment_manager"
        )
        user.write({"groups_id": [(4, manager_group.id)]})
        request.with_user(user).action_reset_to_draft()
        self.assertEqual(request.state, "draft")
