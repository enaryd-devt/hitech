# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class ReplenishmentRequestLine(models.Model):
    """Ligne produit demandée et allocations de source calculées."""

    _name = "replenishment.request.line"
    _description = "Ligne de demande de réapprovisionnement"
    _order = "request_id, sequence, id"

    sequence = fields.Integer(default=10)
    request_id = fields.Many2one("replenishment.request", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", required=True, domain=[("type", "in", ["consu", "product"])] )
    description = fields.Char(compute="_compute_description", store=True, readonly=False)
    product_uom_id = fields.Many2one("uom.uom", required=True, string="UDM")
    quantity_requested = fields.Float(
        required=True, digits="Product Unit of Measure", default=1.0, string="Qté demandé"
    )
    quantity_found = fields.Float(
        compute="_compute_quantity_found", store=True, digits="Product Unit of Measure", string="Disponible"
    )
    packaging_quantity = fields.Float(string="Qté Cdtment", digits="Product Unit of Measure")
    packaging_id = fields.Many2one("product.packaging", string="Cdtment", domain="[('product_id', '=', product_id)]")
    candidate_packaging_ids = fields.Many2many("product.packaging", compute="_compute_candidate_packagings")
    availability = fields.Float(compute="_compute_availability", store=True, digits="Product Unit of Measure")
    status = fields.Selection(
        [("available", "Disponible"), ("partial", "Partiellement disponible"), ("missing", "Indisponible")],
        compute="_compute_status", store=True,
    )
    allocation_ids = fields.One2many("replenishment.allocation", "line_id", copy=True)
    source_location_id = fields.Many2one(
        "stock.location", string="Emplacement source", domain=[("usage", "=", "internal")], index=True
    )
    candidate_source_location_ids = fields.Many2many(
        "stock.location", compute="_compute_candidate_source_locations"
    )
    preferred_location_id = fields.Many2one("stock.location", compute="_compute_preferred_location", store=True)
    state = fields.Selection(related="request_id.state", store=True)

    @api.depends("product_id")
    def _compute_description(self):
        for line in self:
            if line.product_id and not line.description:
                line.description = line.product_id.display_name

    @api.depends(
        "allocation_ids.quantity",
        "product_id",
        "source_location_id",
        "request_id.destination_location_id",
    )
    def _compute_quantity_found(self):
        for line in self:
            if line.product_id and line.source_location_id and line.request_id.destination_location_id:
                quants = line.env["stock.quant"]._get_replenishment_candidates(
                    line.product_id, line.request_id.destination_location_id
                ).filtered(lambda quant: quant.location_id == line.source_location_id)
                line.quantity_found = sum(quants.mapped("available_quantity"))
            else:
                line.quantity_found = sum(line.allocation_ids.mapped("quantity"))

    @api.depends("product_id", "request_id.destination_location_id")
    def _compute_candidate_source_locations(self):
        for line in self:
            line.candidate_source_location_ids = line._get_candidate_source_locations()

    @api.depends("product_id")
    def _compute_candidate_packagings(self):
        for line in self:
            line.candidate_packaging_ids = line._get_product_packagings() if line.product_id else False

    @api.depends("quantity_requested", "quantity_found")
    def _compute_availability(self):
        for line in self:
            line.availability = line.quantity_found - line.quantity_requested

    @api.depends("quantity_requested", "quantity_found")
    def _compute_status(self):
        for line in self:
            precision = line.product_uom_id.rounding or 0.01
            if float_compare(line.quantity_found, line.quantity_requested, precision_rounding=precision) >= 0:
                line.status = "available"
            elif float_is_zero(line.quantity_found, precision_rounding=precision):
                line.status = "missing"
            else:
                line.status = "partial"

    @api.depends("allocation_ids.source_location_id", "allocation_ids.sequence")
    def _compute_preferred_location(self):
        for line in self:
            line.preferred_location_id = line.allocation_ids[:1].source_location_id

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id
            line.description = line.product_id.display_name
            line.source_location_id = False
            line.packaging_id = False
            line._set_packaging_from_quantity()

    @api.onchange("product_id", "quantity_requested", "product_uom_id", "source_location_id", "request_id.destination_location_id")
    def _onchange_allocation_inputs(self):
        for line in self:
            candidate_locations = line._get_candidate_source_locations()
            if line.source_location_id and line.source_location_id not in candidate_locations:
                line.source_location_id = False
            line._prepare_onchange_allocations()
        if len(self) == 1:
            return self._get_line_domain()

    @api.onchange("product_id", "quantity_requested", "product_uom_id")
    def _onchange_packaging_quantity(self):
        for line in self:
            line._set_packaging_from_quantity()
        if len(self) == 1:
            return self._get_line_domain()

    @api.onchange("packaging_id", "packaging_quantity")
    def _onchange_packaging_inputs(self):
        for line in self:
            if line.packaging_id and line.packaging_quantity:
                line.quantity_requested = line.packaging_quantity * line.packaging_id.qty
        if len(self) == 1:
            return self._get_line_domain()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.pop("allocation_ids", None)
            product = self.env["product.product"].browse(vals.get("product_id"))
            if product:
                vals["product_uom_id"] = product.uom_id.id
        lines = super().create(vals_list)
        lines._set_packaging_from_quantity()
        lines._refresh_allocations()
        return lines

    def write(self, vals):
        vals = dict(vals)
        if "product_id" in vals:
            product = self.env["product.product"].browse(vals["product_id"])
            vals["product_uom_id"] = product.uom_id.id
            vals.setdefault("source_location_id", False)
        else:
            vals.pop("product_uom_id", None)
        result = super().write(vals)
        if {"product_id", "quantity_requested", "product_uom_id", "source_location_id", "request_id"} & set(vals):
            if {"product_id", "quantity_requested"} & set(vals) and not {"packaging_id", "packaging_quantity"} & set(vals):
                self._set_packaging_from_quantity()
            self._refresh_allocations()
        return result

    @api.model
    def _prepare_packaging_vals(self, vals, line=False):
        vals = dict(vals)
        if "quantity_requested" not in vals:
            packaging_id = vals.get("product_packaging_id") or (line.product_packaging_id.id if line else False)
            packaging_qty = vals.get("packaging_qty", line.packaging_qty if line else 0.0)
            if packaging_id and packaging_qty:
                packaging = self.env["product.packaging"].browse(packaging_id)
                product = self.env["product.product"].browse(vals.get("product_id")) if vals.get("product_id") else packaging.product_id
                product_uom = self.env["uom.uom"].browse(vals.get("product_uom_id")) if vals.get("product_uom_id") else (line.product_uom_id if line and line.product_uom_id else product.uom_id)
                vals["quantity_requested"] = self._convert_packaging_quantity(packaging, packaging_qty, product_uom)
        return vals

    def _apply_packaging_quantity(self):
        self.ensure_one()
        if self.product_packaging_id and self.packaging_qty:
            self.quantity_requested = self._convert_packaging_quantity(
                self.product_packaging_id, self.packaging_qty, self.product_uom_id
            )

    def _get_packaging_unit_quantity(self):
        self.ensure_one()
        if not self.product_packaging_id:
            return 0.0
        return self._convert_packaging_quantity(self.product_packaging_id, 1.0, self.product_uom_id)

    @api.model
    def _convert_packaging_quantity(self, packaging, packaging_qty, product_uom):
        quantity = (packaging.qty or 0.0) * packaging_qty
        if packaging.product_id and product_uom and packaging.product_id.uom_id != product_uom:
            quantity = packaging.product_id.uom_id._compute_quantity(quantity, product_uom)
        return quantity

    @api.constrains("quantity_requested")
    def _check_quantity_requested(self):
        for line in self:
            if float_compare(line.quantity_requested, 0.0, precision_rounding=line.product_uom_id.rounding or 0.01) <= 0:
                raise ValidationError("La quantité demandée doit être positive.")

    def _prepare_onchange_allocations(self):
        self.ensure_one()
        if not self.product_id or not self.request_id.destination_location_id or not self.quantity_requested:
            return
        commands = [(5, 0, 0)]
        allocation_values = self._get_allocation_values()
        if not self.source_location_id and allocation_values:
            self.source_location_id = allocation_values[0]["source_location_id"]
        for vals in allocation_values:
            commands.append((0, 0, vals))
        self.allocation_ids = commands

    def _refresh_allocations(self):
        for line in self.filtered(lambda item: item.request_id.state == "draft"):
            line.allocation_ids.unlink()
            line.env["replenishment.allocation"].create(line._get_allocation_values())
            candidate_locations = line._get_candidate_source_locations()
            if line.source_location_id and line.source_location_id not in candidate_locations:
                super(ReplenishmentRequestLine, line).write({"source_location_id": False})
            if not line.source_location_id and line.allocation_ids:
                super(ReplenishmentRequestLine, line).write({
                    "source_location_id": line.allocation_ids[:1].source_location_id.id
                })

    def _get_line_domain(self):
        self.ensure_one()
        return {
            "domain": {
                "packaging_id": [("id", "in", self._get_product_packagings().ids)] if self.product_id else [],
                "source_location_id": [
                    ("id", "in", self._get_candidate_source_locations().ids)
                ] if self.product_id and self.request_id.destination_location_id else [("usage", "=", "internal")],
            }
        }

    def _get_candidate_source_locations(self):
        self.ensure_one()
        if not self.product_id or not self.request_id.destination_location_id:
            return self.env["stock.location"]
        quants = self.env["stock.quant"]._get_replenishment_candidates(
            self.product_id, self.request_id.destination_location_id
        )
        return quants.mapped("location_id")

    def _set_packaging_from_quantity(self):
        for line in self:
            packaging = line._get_preferred_packaging(line.quantity_requested) if line.product_id else False
            line.packaging_id = packaging
            line.packaging_quantity = (
                line.quantity_requested / packaging.qty if packaging and packaging.qty else 0.0
            )

    def _format_packaging_quantity(self, quantity):
        self.ensure_one()
        precision = self.product_uom_id.rounding or 0.01
        packaging = self._get_exact_packaging(quantity, precision)
        if not packaging:
            return "%s %s" % (self._format_report_number(quantity), self.product_uom_id.display_name or "Unité(s)")
        package_qty = packaging.qty or 1.0
        package_count = quantity / package_qty if package_qty else quantity
        package_name = (packaging.name or "").upper()
        if float_compare(package_qty, 1.0, precision_rounding=precision) == 0:
            package_label = package_name
        else:
            formatted_package_qty = self._format_report_number(package_qty)
            package_label = package_name
            if formatted_package_qty not in package_name and " DE " not in package_name:
                package_label = "%s DE %s" % (package_name, formatted_package_qty)
        return "%s %s" % (self._format_report_number(package_count), package_label)

    def _get_product_packagings(self):
        self.ensure_one()
        product = self.product_id
        packagings = product.packaging_ids if "packaging_ids" in product._fields else self.env["product.packaging"]
        if not packagings:
            Packaging = self.env["product.packaging"]
            domain = []
            if "product_id" in Packaging._fields:
                domain.append(("product_id", "=", product.id))
            elif "product_tmpl_id" in Packaging._fields:
                domain.append(("product_tmpl_id", "=", product.product_tmpl_id.id))
            if domain:
                packagings = Packaging.search(domain)
        return packagings.filtered(lambda packaging: packaging.qty and packaging.qty > 0).sorted(
            lambda packaging: packaging.qty, reverse=True
        )

    def _get_preferred_packaging(self, quantity):
        self.ensure_one()
        packagings = self._get_product_packagings()
        if not packagings:
            return self.env["product.packaging"]
        smaller_packaging = packagings.filtered(lambda packaging: packaging.qty <= quantity)[:1]
        return smaller_packaging or packagings[:1]

    def _get_exact_packaging(self, quantity, precision):
        self.ensure_one()
        packagings = self._get_product_packagings()
        for packaging in packagings:
            package_qty = packaging.qty
            package_count = quantity / package_qty
            if float_is_zero(package_count - round(package_count), precision_rounding=precision):
                return packaging
        return self.env["product.packaging"]

    @api.model
    def _format_report_number(self, quantity):
        rounded = round(quantity)
        if float_is_zero(quantity - rounded, precision_rounding=0.00001):
            return str(int(rounded))
        return ("%.2f" % quantity).rstrip("0").rstrip(".")

    def _get_allocation_values(self):
        self.ensure_one()
        if not self.product_id or not self.request_id.destination_location_id:
            return []
        qty_left = self.quantity_requested
        values = []
        quants = self.env["stock.quant"]._get_replenishment_candidates(
            self.product_id, self.request_id.destination_location_id
        )
        if self.source_location_id:
            preferred_quants = quants.filtered(lambda quant: quant.location_id == self.source_location_id)
            other_quants = quants.filtered(lambda quant: quant.location_id != self.source_location_id)
            quants = preferred_quants + other_quants
        for index, quant in enumerate(quants, start=1):
            if float_is_zero(qty_left, precision_rounding=self.product_uom_id.rounding or 0.01):
                break
            available = quant.available_quantity
            qty = min(qty_left, available)
            if qty <= 0:
                continue
            values.append({
                "sequence": index * 10,
                "request_id": self.request_id.id,
                "line_id": self.id,
                "source_location_id": quant.location_id.id,
                "quantity": qty,
            })
            qty_left -= qty
        return values
