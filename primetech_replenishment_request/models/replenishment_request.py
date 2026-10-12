# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class ReplenishmentRequest(models.Model):
    """Demande interne qui alloue le stock et crée les transferts immédiats."""

    _name = "replenishment.request"
    _description = "Demande de réapprovisionnement interne"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_request desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Référence", default="Nouveau", readonly=True, copy=False, tracking=True, index=True)
    requester_id = fields.Many2one("res.users", string="Demandeur", default=lambda self: self.env.user, required=True, tracking=True)
    date_request = fields.Datetime(string="Date de demande", default=fields.Datetime.now, required=True, tracking=True)
    destination_location_id = fields.Many2one(
        "stock.location", string="Emplacement de destination", required=True, domain=[("usage", "=", "internal")], tracking=True
    )
    company_id = fields.Many2one("res.company", string="Société", default=lambda self: self.env.company, required=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Devise", readonly=True)
    define_transfer_cost = fields.Boolean(string="Définir le coût de transfert", tracking=True)
    transfer_cost_amount = fields.Monetary(string="Coût de transfert", currency_field="currency_id", tracking=True)
    transfer_cost_allocation_method = fields.Selection(
        [
            ("quantity", "Par quantité"),
            ("volume", "Par volume"),
            ("weight", "Par poids"),
            ("equal", "Égal"),
        ],
        string="Méthode de répartition",
        default="quantity",
        tracking=True,
    )
    warehouse_id = fields.Many2one("stock.warehouse", string="Entrepôt", compute="_compute_warehouse", store=True, index=True)
    comments = fields.Text(string="Commentaires", tracking=True)
    state = fields.Selection(
        [("draft", "Brouillon"), ("to_approve", "À approuver"), ("approved", "Approuvée"), ("cancelled", "Annulée")],
        default="draft", string="État", required=True, tracking=True, index=True,
    )
    line_ids = fields.One2many("replenishment.request.line", "request_id", copy=True)
    allocation_ids = fields.One2many("replenishment.allocation", "request_id", copy=True)
    picking_ids = fields.One2many("stock.picking", "replenishment_request_id", readonly=True, copy=False)
    transfer_cost_valuation_layer_ids = fields.One2many("stock.valuation.layer", "replenishment_request_id", readonly=True, copy=False)
    picking_count = fields.Integer(string="Transferts", compute="_compute_counts")
    attachment_count = fields.Integer(string="Pièces jointes", compute="_compute_counts")
    history_count = fields.Integer(string="Historique", compute="_compute_counts")
    activity_count = fields.Integer(string="Activités", compute="_compute_counts")
    has_missing_stock = fields.Boolean(string="Stock manquant", compute="_compute_has_missing_stock")

    @api.depends("destination_location_id")
    def _compute_warehouse(self):
        warehouses = self.env["stock.warehouse"].search([])
        for request in self:
            request.warehouse_id = warehouses.filtered(
                lambda wh: request.destination_location_id
                and request.destination_location_id.id in wh.view_location_id.child_internal_location_ids.ids
            )[:1]

    @api.depends("picking_ids", "message_ids", "activity_ids")
    def _compute_counts(self):
        Attachment = self.env["ir.attachment"]
        for request in self:
            request.picking_count = len(request.picking_ids)
            request.attachment_count = Attachment.search_count([
                ("res_model", "=", request._name), ("res_id", "=", request.id)
            ])
            request.history_count = len(request.message_ids)
            request.activity_count = len(request.activity_ids)

    @api.depends("line_ids.status")
    def _compute_has_missing_stock(self):
        for request in self:
            request.has_missing_stock = any(line.status != "available" for line in request.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code("replenishment.request") or "Nouveau"
            if not vals.get("destination_location_id"):
                location_id = self.env["ir.config_parameter"].sudo().get_param("primetech_replenishment_request.default_destination_location_id")
                if location_id:
                    vals["destination_location_id"] = int(location_id)
        requests = super().create(vals_list)
        requests._message_state_change("draft")
        return requests

    def copy(self, default=None):
        default = dict(default or {}, name="Nouveau", state="draft", picking_ids=False)
        return super().copy(default)

    def unlink(self):
        if any(request.state not in ("draft", "cancelled") for request in self):
            raise UserError(_("Seules les demandes en brouillon ou annulées peuvent être supprimées."))
        return super().unlink()

    def action_submit(self):
        self._validate_ready()
        self.write({"state": "to_approve"})
        self._notify_state("to_approve")

    def action_approve(self):
        self._validate_ready(require_full_stock=True)
        for request in self:
            request._create_and_validate_pickings()
            if request.picking_ids and all(picking.state == "done" for picking in request.picking_ids):
                request._create_transfer_cost_valuation_layers()
        self.write({"state": "approved"})
        self._notify_state("approved")

    def action_cancel(self):
        self.write({"state": "cancelled"})
        self._notify_state("cancelled")

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "primetech_replenishment_request.group_replenishment_manager"
        ):
            raise AccessError(_("Seul un responsable peut remettre une demande en brouillon."))
        requests = self.filtered(lambda request: request.state != "draft")
        if any(request.picking_ids for request in requests):
            raise UserError(
                _(
                    "Une demande liée à un transfert ne peut pas être remise en brouillon. "
                    "Annulez ou traitez d’abord le transfert concerné."
                )
            )
        requests.write({"state": "draft"})
        requests._notify_state("draft")

    def action_view_pickings(self):
        self.ensure_one()
        return self._window_action("stock.action_picking_tree_all", [("id", "in", self.picking_ids.ids)])

    def action_view_attachments(self):
        self.ensure_one()
        return self._window_action("base.action_attachment", [("res_model", "=", self._name), ("res_id", "=", self.id)])

    def action_view_history(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Historique"), "res_model": "mail.message", "view_mode": "list,form", "domain": [("model", "=", self._name), ("res_id", "=", self.id)]}

    def _window_action(self, xmlid, domain):
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        action["domain"] = domain
        return action

    def _validate_ready(self, require_full_stock=False):
        for request in self:
            if not request.line_ids:
                raise ValidationError(_("Ajoutez au moins une ligne de produit."))
            if request.define_transfer_cost:
                currency = request.currency_id or request.env.company.currency_id
                if float_compare(request.transfer_cost_amount, 0.0, precision_rounding=currency.rounding) <= 0:
                    raise ValidationError(_("Le coût de transfert doit être strictement positif."))
                if not request.transfer_cost_allocation_method:
                    raise ValidationError(_("Choisissez une méthode de répartition du coût de transfert."))
            for line in request.line_ids:
                line._refresh_allocations()
                if require_full_stock and line.status != "available":
                    raise ValidationError(_("Stock insuffisant pour %s.") % line.product_id.display_name)

    def _create_and_validate_pickings(self):
        self.ensure_one()
        picking_type = self.env.ref("stock.picking_type_internal", raise_if_not_found=False)
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([("code", "=", "internal")], limit=1)
        grouped = defaultdict(lambda: self.env["replenishment.allocation"])
        for allocation in self.allocation_ids:
            grouped[allocation.source_location_id] |= allocation
        for source, allocations in grouped.items():
            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": self.destination_location_id.id,
                "origin": self.name,
                "replenishment_request_id": self.id,
            })
            for allocation in allocations:
                move = self.env["stock.move"].create({
                    "name": allocation.line_id.description or allocation.product_id.display_name,
                    "product_id": allocation.product_id.id,
                    "product_uom_qty": allocation.quantity,
                    "product_uom": allocation.product_uom_id.id,
                    "location_id": source.id,
                    "location_dest_id": self.destination_location_id.id,
                    "picking_id": picking.id,
                })
                allocation.write({"picking_id": picking.id, "move_id": move.id})
            picking.action_confirm()
            picking.action_assign()
            auto_validate = self.env["ir.config_parameter"].sudo().get_param(
                "primetech_replenishment_request.auto_validate_transfers", "True"
            )
            if auto_validate != "False":
                self._set_done_quantities(picking)
                picking.button_validate()
                if picking.state != "done":
                    picking._action_done()

    def _create_transfer_cost_valuation_layers(self):
        for request in self.filtered(lambda item: item.define_transfer_cost and not item.transfer_cost_valuation_layer_ids):
            if not request.picking_ids or any(picking.state != "done" for picking in request.picking_ids):
                continue
            product_amounts = request._get_transfer_cost_amounts_by_product()
            StockValuationLayer = request.env["stock.valuation.layer"].sudo()
            moves_by_product = {move.product_id.id: move for move in request.picking_ids.move_ids.filtered(lambda move: move.state == "done")}
            for product_id, amount in product_amounts.items():
                StockValuationLayer.create({
                    "product_id": product_id,
                    "value": amount,
                    "quantity": 0.0,
                    "unit_cost": 0.0,
                    "description": _("Coût logistique du transfert %s") % request.name,
                    "stock_move_id": moves_by_product.get(product_id, request.env["stock.move"]).id or False,
                    "company_id": request.company_id.id,
                    "replenishment_request_id": request.id,
                })

    def _get_transfer_cost_amounts_by_product(self):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        product_quantities = defaultdict(float)
        for allocation in self.allocation_ids:
            product_quantities[allocation.product_id.id] += allocation.product_uom_id._compute_quantity(
                allocation.quantity, allocation.product_id.uom_id
            )
        factors = {}
        for product_id, quantity in product_quantities.items():
            product = self.env["product.product"].browse(product_id)
            if self.transfer_cost_allocation_method == "quantity":
                factor = quantity
            elif self.transfer_cost_allocation_method == "volume":
                factor = quantity * (product.volume or 0.0)
            elif self.transfer_cost_allocation_method == "weight":
                factor = quantity * (product.weight or 0.0)
            else:
                factor = 1.0
            if not float_is_zero(factor, precision_rounding=0.000001):
                factors[product_id] = factor
        if not factors:
            method_label = dict(self._fields["transfer_cost_allocation_method"].selection).get(
                self.transfer_cost_allocation_method
            )
            raise ValidationError(_("Impossible de répartir le coût de transfert avec la méthode %s.") % method_label)
        total_factor = sum(factors.values())
        products = list(factors)
        amounts = {}
        allocated_amount = 0.0
        for product_id in products[:-1]:
            amount = float_round(
                self.transfer_cost_amount * factors[product_id] / total_factor,
                precision_rounding=currency.rounding,
            )
            amounts[product_id] = amount
            allocated_amount += amount
        amounts[products[-1]] = self.transfer_cost_amount - allocated_amount
        return amounts

    def _set_done_quantities(self, picking):
        MoveLine = self.env["stock.move.line"]
        qty_field = "quantity" if "quantity" in MoveLine._fields else "qty_done"
        for move in picking.move_ids:
            if move.move_line_ids:
                for line in move.move_line_ids:
                    line[qty_field] = self._get_move_line_reserved_quantity(line, move)
            else:
                vals = {
                    "picking_id": picking.id,
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    qty_field: move.product_uom_qty,
                }
                MoveLine.create(vals)

    def _get_move_line_reserved_quantity(self, line, move):
        for field_name in ("reserved_uom_qty", "reserved_qty", "product_uom_qty", "quantity"):
            if field_name in line._fields:
                quantity = line[field_name]
                if quantity:
                    return quantity
        return move.product_uom_qty

    def _notify_state(self, state):
        self._message_state_change(state)
        if state in ("to_approve", "approved"):
            self._schedule_state_activity(state)
        self._send_state_email(state)

    def _message_state_change(self, state):
        labels = dict(self._fields["state"].selection)
        for request in self:
            request.message_post(body=_("Demande passée à l’état %s.") % labels.get(state, state))

    def _schedule_state_activity(self, state):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        group_xmlid = "primetech_replenishment_request.group_replenishment_manager" if state == "to_approve" else "primetech_replenishment_request.group_replenishment_stockman"
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        users = group.users if group else self.env.user
        for request in self:
            for user in users:
                request.activity_schedule(activity_type_id=activity_type.id, user_id=user.id, summary=request.name)

    def _send_state_email(self, state):
        template = self.env.ref("primetech_replenishment_request.email_template_replenishment_state", raise_if_not_found=False)
        for request in self:
            if template and request.requester_id.email:
                template.with_context(state_label=dict(request._fields["state"].selection).get(state)).send_mail(request.id, force_send=False)
