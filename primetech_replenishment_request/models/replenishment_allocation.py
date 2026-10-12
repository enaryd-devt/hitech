# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class ReplenishmentAllocation(models.Model):
    """Stock allocation proposed for a replenishment request line."""

    _name = "replenishment.allocation"
    _description = "Allocation de réapprovisionnement"
    _order = "request_id, line_id, sequence, id"

    sequence = fields.Integer(default=10)
    request_id = fields.Many2one(
        "replenishment.request", required=True, ondelete="cascade", index=True
    )
    line_id = fields.Many2one(
        "replenishment.request.line", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one(related="line_id.product_id", store=True, readonly=True)
    source_location_id = fields.Many2one(
        "stock.location", required=True, domain=[("usage", "=", "internal")], index=True
    )
    destination_location_id = fields.Many2one(related="request_id.destination_location_id", store=True)
    product_uom_id = fields.Many2one(related="line_id.product_uom_id", store=True, readonly=True)
    quantity = fields.Float(required=True, digits="Product Unit of Measure")
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    move_id = fields.Many2one("stock.move", readonly=True, copy=False)
    state = fields.Selection(related="request_id.state", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("request_id") and vals.get("line_id"):
                line = self.env["replenishment.request.line"].browse(vals["line_id"])
                vals["request_id"] = line.request_id.id
        return super().create(vals_list)

    @api.constrains("quantity")
    def _check_quantity(self):
        for allocation in self:
            precision = allocation.product_uom_id.rounding or 0.01
            if float_compare(allocation.quantity, 0.0, precision_rounding=precision) <= 0:
                raise ValidationError("La quantité allouée doit être positive.")
