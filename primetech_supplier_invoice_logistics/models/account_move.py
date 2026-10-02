# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model_create_multi
    def create(self, vals_list):
        """Always date supplier bills created from the standard form or API."""
        today = fields.Date.context_today(self)
        default_move_type = self.env.context.get("default_move_type")
        for vals in vals_list:
            move_type = vals.get("move_type", default_move_type)
            if move_type in ("in_invoice", "in_refund") and not vals.get("invoice_date"):
                vals["invoice_date"] = today
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        """Pre-fill the supplier invoice date when the user leaves it empty."""
        values = super().default_get(fields_list)
        move_type = values.get("move_type") or self.env.context.get("default_move_type")
        if (
            "invoice_date" in fields_list
            and move_type in ("in_invoice", "in_refund")
            and not values.get("invoice_date")
        ):
            values["invoice_date"] = fields.Date.context_today(self)
        return values

    @api.onchange("move_type")
    def _onchange_primetech_supplier_invoice_date(self):
        """Fill the supplier bill date immediately in the interactive form."""
        for move in self:
            if move.move_type in ("in_invoice", "in_refund") and not move.invoice_date:
                move.invoice_date = fields.Date.context_today(move)

    primetech_apply_discount = fields.Boolean(string="Appliquer réduction")
    primetech_discount_account_id = fields.Many2one(
        "account.account", string="Compte réduction", check_company=True,
        domain="[('company_ids', 'in', company_id)]",
    )
    primetech_discount_type = fields.Selection(
        [("percentage", "Pourcentage"), ("fixed", "Montant fixe")],
        string="Type réduction", default="percentage",
    )
    primetech_discount_value = fields.Float(string="Valeur réduction", default=0.0)
    primetech_discount_amount = fields.Monetary(
        string="Montant réduction", compute="_compute_primetech_discount_totals",
        currency_field="currency_id",
    )
    primetech_amount_untaxed_after_discount = fields.Monetary(
        string="Total HT après réduction", compute="_compute_primetech_discount_totals",
        currency_field="currency_id",
    )
    primetech_amount_after_discount = fields.Monetary(
        string="Montant après réduction", compute="_compute_primetech_discount_totals",
        currency_field="currency_id",
    )
    primetech_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Branche / entrepôt", check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    primetech_picking_type_id = fields.Many2one(
        "stock.picking.type", string="Type de réception", check_company=True,
        domain="[('code', '=', 'incoming'), ('company_id', '=', company_id)]",
    )
    primetech_stock_location_id = fields.Many2one(
        "stock.location", string="Emplacement de stock", check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
    )
    primetech_calculation_basis = fields.Selection(
        [("weight", "Poids"), ("volume", "Volume")],
        string="Calcul selon le", default="weight", required=True,
    )
    primetech_weight_rate = fields.Float(string="Taux poids", digits="Product Price")
    primetech_volume_rate = fields.Float(string="Taux volume", digits="Product Price")
    primetech_exchange_rate = fields.Float(
        string="Taux de change", default=1.0, digits="Product Price",
        help="Taux informatif utilisé par les calculs logistiques spécifiques.",
    )
    primetech_display_exchange_rate = fields.Float(
        string="Taux",
        compute="_compute_primetech_display_exchange_rate",
        inverse="_inverse_primetech_display_exchange_rate",
        digits="Product Price",
        help="Montant en devise de la société pour une unité de la devise de la facture."
             " Exemple : 1 USD = 675 FCFA.",
    )
    primetech_total_units = fields.Float(
        string="Total unités", compute="_compute_primetech_logistics_totals", store=True,
    )
    primetech_total_weight_volume = fields.Float(
        string="Total poids/volume", compute="_compute_primetech_logistics_totals", store=True,
    )
    primetech_total_weight = fields.Float(
        string="Total poids", compute="_compute_primetech_logistics_totals",
        store=True, digits=(16, 5),
    )
    primetech_total_volume = fields.Float(
        string="Total volume", compute="_compute_primetech_logistics_totals",
        store=True, digits=(16, 5),
    )
    primetech_total_cost = fields.Monetary(
        string="Total coût de revient", compute="_compute_primetech_logistics_totals",
        store=True, currency_field="company_currency_id",
    )
    primetech_total_constant = fields.Monetary(
        string="Total constante", compute="_compute_primetech_logistics_totals",
        store=True, currency_field="company_currency_id",
    )
    primetech_receipt_picking_ids = fields.Many2many(
        "stock.picking", "primetech_invoice_receipt_rel", "move_id", "picking_id",
        string="Réceptions liées", copy=False, readonly=True,
    )
    primetech_receipt_picking_count = fields.Integer(
        compute="_compute_primetech_receipt_picking_count", string="Réceptions",
    )

    @api.depends(
        "amount_untaxed", "amount_total", "primetech_apply_discount",
        "primetech_discount_type", "primetech_discount_value",
    )
    def _compute_primetech_discount_totals(self):
        for move in self:
            discount = 0.0
            if move.primetech_apply_discount:
                if move.primetech_discount_type == "percentage":
                    discount = move.amount_untaxed * (move.primetech_discount_value or 0.0) / 100.0
                else:
                    discount = move.primetech_discount_value or 0.0
            discount = min(max(discount, 0.0), move.amount_untaxed)
            move.primetech_discount_amount = discount
            move.primetech_amount_untaxed_after_discount = move.amount_untaxed - discount
            move.primetech_amount_after_discount = move.amount_total - discount

    @api.depends(
        "invoice_line_ids.quantity", "invoice_line_ids.primetech_weight",
        "invoice_line_ids.primetech_volume", "invoice_line_ids.primetech_final_cost",
        "invoice_line_ids.primetech_constant_cost",
        "invoice_line_ids.primetech_weight_cost",
        "invoice_line_ids.primetech_volume_cost",
        "invoice_line_ids.primetech_cost_by_weight",
        "invoice_line_ids.primetech_cost_by_volume",
        "primetech_calculation_basis",
    )
    def _compute_primetech_logistics_totals(self):
        for move in self:
            # Odoo 18 identifies regular invoice articles with
            # ``display_type == 'product'``.  They must be included while
            # sections and notes remain excluded from logistics totals.
            lines = move.invoice_line_ids.filtered(
                lambda line: line.display_type in (False, "product")
            )
            move.primetech_total_units = sum(lines.mapped("quantity"))
            measure_field = (
                "primetech_weight" if move.primetech_calculation_basis == "weight"
                else "primetech_volume"
            )
            # Weight/volume are unit values on invoice lines; the dashboard
            # footer must therefore sum each measure multiplied by quantity.
            move.primetech_total_weight = sum(
                (line.primetech_weight or 0.0) * (line.quantity or 0.0)
                for line in lines
            )
            move.primetech_total_volume = sum(
                (line.primetech_volume or 0.0) * (line.quantity or 0.0)
                for line in lines
            )
            move.primetech_total_weight_volume = sum(
                (line[measure_field] or 0.0) * (line.quantity or 0.0)
                for line in lines
            )
            automatic_cost_field = (
                "primetech_cost_by_weight"
                if move.primetech_calculation_basis == "weight"
                else "primetech_cost_by_volume"
            )
            automatic_constant_field = (
                "primetech_weight_cost"
                if move.primetech_calculation_basis == "weight"
                else "primetech_volume_cost"
            )
            # The final cost is optional. Until it is entered, show the
            # logistics proposal so the dashboard never stays empty while
            # the supplier-bill grid is being completed.
            move.primetech_total_cost = sum(
                line.primetech_final_cost or line[automatic_cost_field] or 0.0
                for line in lines
            )
            move.primetech_total_constant = sum(
                line.primetech_constant_cost or line[automatic_constant_field] or 0.0
                for line in lines
            )

    @api.depends("primetech_receipt_picking_ids")
    def _compute_primetech_receipt_picking_count(self):
        for move in self:
            move.primetech_receipt_picking_count = len(move.primetech_receipt_picking_ids)

    @api.onchange("primetech_warehouse_id")
    def _onchange_primetech_warehouse_id(self):
        for move in self:
            warehouse = move.primetech_warehouse_id
            if warehouse:
                move.primetech_picking_type_id = warehouse.in_type_id
                move.primetech_stock_location_id = warehouse.lot_stock_id

    @api.onchange(
        "invoice_currency_rate", "primetech_display_exchange_rate", "primetech_weight_rate", "primetech_volume_rate",
        "primetech_calculation_basis", "invoice_line_ids",
    )
    def _onchange_primetech_logistics(self):
        """Refresh the logistics footer immediately after any line edit.

        A simple ``invoice_line_ids`` onchange only reacts to adding/removing
        a line.  The explicit dotted fields are necessary for the totals to
        be recalculated while the user edits an existing article line.
        """
        for move in self:
            for line in move.invoice_line_ids.filtered(
                lambda item: item.display_type in (False, "product")
            ):
                line._compute_primetech_logistics()
            move._compute_primetech_logistics_totals()

    @api.depends("currency_id", "company_currency_id", "invoice_currency_rate")
    def _compute_primetech_display_exchange_rate(self):
        """Show the bill currency first: for example, 1 USD = 675 FCFA."""
        for move in self:
            if (
                not move.currency_id
                or not move.company_currency_id
                or move.currency_id == move.company_currency_id
            ):
                move.primetech_display_exchange_rate = 1.0
                continue
            internal_rate = move.invoice_currency_rate or 0.0
            move.primetech_display_exchange_rate = 1.0 / internal_rate if internal_rate else 0.0

    def _inverse_primetech_display_exchange_rate(self):
        """Convert the supplier-facing rate back to Odoo's internal rate."""
        for move in self:
            if move.currency_id and move.company_currency_id and move.currency_id != move.company_currency_id:
                displayed_rate = move.primetech_display_exchange_rate or 0.0
                if displayed_rate > 0:
                    move.invoice_currency_rate = 1.0 / displayed_rate

    @api.onchange("currency_id", "company_id", "invoice_date")
    def _onchange_primetech_daily_currency_rate(self):
        """Use the current Odoo currency rate as soon as a bill is prepared.

        Odoo's currency table is the reliable, auditable source for daily
        international rates.  It is also what the native refresh action uses,
        so the amount displayed as ``1 USD = ... FCFA`` and all accounting
        calculations always use exactly the same rate.
        """
        for move in self:
            if (
                move.move_type not in ("in_invoice", "in_refund")
                or not move.currency_id
                or not move.company_currency_id
                or move.currency_id == move.company_currency_id
            ):
                continue
            rate_date = move.invoice_date or fields.Date.context_today(move)
            rate = self.env["res.currency"]._get_conversion_rate(
                move.company_currency_id,
                move.currency_id,
                move.company_id,
                rate_date,
            )
            if rate > 0:
                move.invoice_currency_rate = rate

    def action_post(self):
        result = super().action_post()
        for move in self.filtered(lambda item: item.move_type == "in_invoice"):
            move.sudo()._primetech_create_receipt_picking()
            # The final selling price validated on the supplier bill becomes
            # the active sale price of each received product.
            for line in move.invoice_line_ids.filtered(
                lambda item: not item.display_type and item.product_id and item.primetech_final_sale_price > 0
            ):
                line.product_id.lst_price = line.primetech_final_sale_price
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Also cover invoices imported directly in the posted state."""
        for values in vals_list:
            move_type = values.get("move_type") or self.env.context.get("default_move_type")
            if move_type in ("in_invoice", "in_refund") and not values.get("invoice_date"):
                values["invoice_date"] = fields.Date.context_today(self)
        moves = super().create(vals_list)
        for move in moves.filtered(
            lambda item: item.move_type == "in_invoice" and item.state == "posted"
        ):
            move.sudo()._primetech_create_receipt_picking()
        return moves

    def write(self, vals):
        """Cover every posting flow, including custom modules bypassing action_post."""
        result = super().write(vals)
        if vals.get("state") == "posted":
            for move in self.filtered(lambda item: item.move_type == "in_invoice"):
                move.sudo()._primetech_create_receipt_picking()
        return result

    def _primetech_create_receipt_picking(self):
        self.ensure_one()
        if self.primetech_receipt_picking_ids:
            return self.primetech_receipt_picking_ids
        # In Odoo 18, a normal product line has display_type="product".
        # Sections, notes and accounting-only lines must not become stock moves.
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product")
            and line.product_id and line.quantity > 0
        )
        if not lines:
            return self.env["stock.picking"]
        picking_type = self.primetech_picking_type_id
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([
                ("code", "=", "incoming"), ("company_id", "=", self.company_id.id),
            ], limit=1)
        if not picking_type:
            return self.env["stock.picking"]
        destination = (
            self.primetech_stock_location_id
            or picking_type.default_location_dest_id
            or picking_type.warehouse_id.lot_stock_id
        )
        if not destination:
            raise UserError(_(
                "Configurez un emplacement de destination sur la facture ou "
                "sur le type de réception avant de confirmer la facture."
            ))
        source = (
            picking_type.default_location_src_id
            or self.partner_id.property_stock_supplier
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "origin": self.name or self.ref,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "company_id": self.company_id.id,
            "scheduled_date": self.invoice_date or fields.Datetime.now(),
        })
        for line in lines:
            self.env["stock.move"].create({
                "name": line.name or line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_uom_id.id,
                "picking_id": picking.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "company_id": self.company_id.id,
            })
        picking.action_confirm()
        self.primetech_receipt_picking_ids = [(4, picking.id)]
        return picking

    def action_create_primetech_receipt(self):
        """Create the receipt linked to this supplier bill, without posting it."""
        self.ensure_one()
        if self.move_type != "in_invoice" or self.state not in ("draft", "posted"):
            raise UserError(_("La réception peut uniquement être créée pour une facture fournisseur."))
        self.sudo()._primetech_create_receipt_picking()
        # Remain on the supplier bill and refresh the smart button.
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_view_primetech_receipts(self):
        self.ensure_one()
        if len(self.primetech_receipt_picking_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "res_id": self.primetech_receipt_picking_ids.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
                "context": {"create": False},
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action["domain"] = [("id", "in", self.primetech_receipt_picking_ids.ids)]
        action["context"] = {"create": False}
        return action


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.onchange("primetech_weight")
    def _onchange_primetech_weight_manual_value(self):
        """Keep a weight entered in the invoice grid before recomputing."""
        for line in self:
            line.primetech_weight_manual = line.primetech_weight or 0.0
            line.primetech_weight_is_manual = True

    @api.onchange("primetech_volume")
    def _onchange_primetech_volume_manual_value(self):
        """Keep a volume entered in the invoice grid before recomputing."""
        for line in self:
            line.primetech_volume_manual = line.primetech_volume or 0.0
            line.primetech_volume_is_manual = True

    @api.onchange(
        "product_id", "quantity", "price_unit", "primetech_weight",
        "primetech_volume", "primetech_constant_cost", "primetech_final_cost",
    )
    def _onchange_primetech_refresh_move_logistics_totals(self):
        """Propagate each grid edit to the logistics totals of the bill.

        Editing an existing one2many row does not reliably invoke an onchange
        on the parent record in the web client.  Performing the refresh from
        the line guarantees an immediate update of the supplier-bill footer.
        """
        for line in self:
            if (
                not line.move_id
                or line.display_type not in (False, "product")
            ):
                continue
            line._compute_primetech_logistics()
            line.move_id._compute_primetech_logistics_totals()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "primetech_weight" in vals:
                vals["primetech_weight_manual"] = vals["primetech_weight"]
                vals["primetech_weight_is_manual"] = True
            if "primetech_volume" in vals:
                vals["primetech_volume_manual"] = vals["primetech_volume"]
                vals["primetech_volume_is_manual"] = True
        lines = super().create(vals_list)
        lines.mapped("move_id")._compute_primetech_logistics_totals()
        return lines

    def write(self, vals):
        vals = dict(vals)
        if "primetech_weight" in vals:
            vals["primetech_weight_manual"] = vals["primetech_weight"]
            vals["primetech_weight_is_manual"] = True
        if "primetech_volume" in vals:
            vals["primetech_volume_manual"] = vals["primetech_volume"]
            vals["primetech_volume_is_manual"] = True
        result = super().write(vals)
        if {
            "product_id", "quantity", "price_unit", "primetech_weight",
            "primetech_volume", "primetech_constant_cost", "primetech_final_cost",
        }.intersection(vals):
            self.mapped("move_id")._compute_primetech_logistics_totals()
        return result

    def unlink(self):
        moves = self.mapped("move_id")
        result = super().unlink()
        moves._compute_primetech_logistics_totals()
        return result

    @api.constrains("product_id", "display_type", "move_id")
    def _check_primetech_supplier_line_product(self):
        """A supplier-bill product line is never meaningful without an item.

        Sections and notes remain valid Odoo lines.  The check deliberately
        applies only to supplier invoices/refunds so journal entries and other
        standard accounting flows are unaffected.
        """
        for line in self:
            if (
                line.move_id.move_type in ("in_invoice", "in_refund")
                and line.display_type in (False, "product")
                and not line.product_id
            ):
                raise ValidationError(_("Veuillez sélectionner un article avant d'enregistrer cette ligne."))

    primetech_product_image = fields.Image(
        related="product_id.image_1920", string="Image", readonly=True,
    )
    primetech_weight = fields.Float(
        string="Poids", compute="_compute_primetech_logistics", digits=(16, 6),
        inverse="_inverse_primetech_weight", store=True,
    )
    primetech_weight_manual = fields.Float(digits=(16, 6), copy=False)
    primetech_weight_is_manual = fields.Boolean(copy=False)
    primetech_volume = fields.Float(
        string="Volume", compute="_compute_primetech_logistics", digits=(16, 6),
        inverse="_inverse_primetech_volume", store=True,
    )
    primetech_volume_manual = fields.Float(digits=(16, 6), copy=False)
    primetech_volume_is_manual = fields.Boolean(copy=False)
    primetech_last_price = fields.Monetary(
        string="Dernier Prix", compute="_compute_primetech_logistics", currency_field="currency_id",
    )
    primetech_stock_quantity = fields.Float(
        string="Stock actuel", compute="_compute_primetech_logistics",
        help="Quantité actuellement disponible pour l'article dans Odoo.",
    )
    primetech_last_real_price = fields.Monetary(
        string="Dernier Prix Réel", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_real_price = fields.Monetary(
        string="Prix réel", compute="_compute_primetech_logistics", store=True, currency_field="company_currency_id",
    )
    primetech_weight_cost = fields.Monetary(
        string="Const poids", compute="_compute_primetech_logistics", store=True, currency_field="company_currency_id",
    )
    primetech_volume_cost = fields.Monetary(
        string="Const volume", compute="_compute_primetech_logistics", store=True, currency_field="company_currency_id",
    )
    primetech_constant_cost = fields.Monetary(
        string="Constante", default=0.0, currency_field="company_currency_id",
    )
    primetech_cost_by_weight = fields.Monetary(
        string="CR.poids", compute="_compute_primetech_logistics", store=True, currency_field="company_currency_id",
    )
    primetech_cost_by_volume = fields.Monetary(
        string="CR.volume", compute="_compute_primetech_logistics", store=True, currency_field="company_currency_id",
    )
    primetech_last_final_purchase_cost = fields.Monetary(
        string="Dernier coût d’achat final", compute="_compute_primetech_logistics",
        currency_field="company_currency_id", readonly=True,
        help="Coût de revient final renseigné sur la dernière facture fournisseur validée pour cet article.",
    )
    primetech_final_cost = fields.Monetary(
        string="Cout.R Final", compute="_compute_primetech_logistics",
        inverse="_inverse_primetech_final_cost", store=True, currency_field="company_currency_id",
    )
    primetech_final_cost_manual = fields.Monetary(currency_field="company_currency_id", copy=False)
    primetech_final_cost_is_manual = fields.Boolean(copy=False)
    primetech_final_sale_price = fields.Monetary(
        string="Prix V Final", compute="_compute_primetech_logistics",
        inverse="_inverse_primetech_final_sale_price", store=True, currency_field="company_currency_id",
    )
    primetech_final_sale_price_manual = fields.Monetary(currency_field="company_currency_id", copy=False)
    primetech_final_sale_price_is_manual = fields.Boolean(copy=False)
    primetech_sale_price_by_weight = fields.Monetary(
        string="P.V. poids", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_sale_price_by_volume = fields.Monetary(
        string="P.V. volume", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_last_final_sale_price = fields.Monetary(
        string="Dernier Prix de V final", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_cost_percentage = fields.Float(
        related="product_id.categ_id.primetech_cost_percentage", string="% revient catégorie", readonly=True,
    )
    primetech_sale_percentage = fields.Float(
        related="product_id.categ_id.primetech_sale_percentage", string="% vente catégorie", readonly=True,
    )

    def _inverse_primetech_weight(self):
        for line in self:
            line.primetech_weight_manual = line.primetech_weight
            line.primetech_weight_is_manual = True

    def _inverse_primetech_volume(self):
        for line in self:
            line.primetech_volume_manual = line.primetech_volume
            line.primetech_volume_is_manual = True

    def _inverse_primetech_final_cost(self):
        for line in self:
            line.primetech_final_cost_manual = line.primetech_final_cost
            line.primetech_final_cost_is_manual = True

    def _inverse_primetech_final_sale_price(self):
        for line in self:
            line.primetech_final_sale_price_manual = line.primetech_final_sale_price
            line.primetech_final_sale_price_is_manual = True

    @api.depends(
        "product_id", "quantity", "price_unit", "primetech_constant_cost",
        "product_id.categ_id.primetech_cost_percentage",
        "product_id.categ_id.primetech_sale_percentage",
        "primetech_weight_manual", "primetech_weight_is_manual",
        "primetech_volume_manual", "primetech_volume_is_manual",
        "primetech_final_cost_manual", "primetech_final_cost_is_manual",
        "primetech_final_sale_price_manual", "primetech_final_sale_price_is_manual",
        "move_id.primetech_weight_rate", "move_id.primetech_volume_rate",
        "move_id.primetech_calculation_basis",
        "move_id.invoice_currency_rate",
        "currency_id", "company_currency_id",
    )
    def _compute_primetech_logistics(self):
        for line in self:
            product = line.product_id
            quantity = line.quantity or 0.0
            # Store the physical measure for one unit.  Totals and freight
            # calculations explicitly multiply it by the invoice quantity.
            computed_weight = product.weight or 0.0
            computed_volume = product.volume or 0.0
            line.primetech_weight = line.primetech_weight_manual if line.primetech_weight_is_manual else computed_weight
            line.primetech_volume = line.primetech_volume_manual if line.primetech_volume_is_manual else computed_volume
            line.primetech_stock_quantity = product.qty_available if product else 0.0
            previous = self.search([
                ("id", "!=", line.id), ("move_id", "!=", line.move_id.id),
                ("product_id", "=", product.id),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "=", "posted"),
                ("company_id", "=", line.company_id.id),
            ], order="date desc, id desc", limit=1) if product else self.env["account.move.line"]
            if previous:
                # Bridge the historic supplier price through the company
                # currency, then express it in the currency of the invoice
                # currently being edited. This keeps "Dernier Prix" useful
                # when two supplier bills use different currencies.
                if previous.currency_id == previous.company_currency_id:
                    previous_real_price = previous.price_unit or 0.0
                else:
                    previous_rate = previous.move_id.invoice_currency_rate or 1.0
                    previous_real_price = (previous.price_unit or 0.0) / previous_rate
                previous_real_price = previous.company_currency_id.round(previous_real_price)
                if line.currency_id == line.company_currency_id:
                    last_price = previous_real_price
                else:
                    current_rate = line.move_id.invoice_currency_rate or 1.0
                    last_price = previous_real_price * current_rate
                line.primetech_last_price = line.currency_id.round(last_price)
                line.primetech_last_real_price = previous_real_price
                # The field is deliberately sourced from the *final cost* of
                # the latest posted supplier bill, not from the supplier unit
                # price nor from either automatic cost proposal.
                line.primetech_last_final_purchase_cost = previous.primetech_final_cost or 0.0
            else:
                line.primetech_last_price = 0.0
                line.primetech_last_real_price = 0.0
                line.primetech_last_final_purchase_cost = 0.0
            # invoice_currency_rate is the number of supplier-currency units
            # for one company-currency unit. Example: 1 FCFA = 30 NGN.
            # The real price is therefore always expressed in the company
            # currency (FCFA): supplier price in NGN / 30.
            if line.currency_id == line.company_currency_id:
                real_price = line.price_unit or 0.0
            else:
                conversion_rate = line.move_id.invoice_currency_rate or 1.0
                real_price = (line.price_unit or 0.0) / conversion_rate
            line.primetech_real_price = line.company_currency_id.round(real_price)
            air_sale_factor = 1 + (line.primetech_sale_percentage or 0.0) / 100.0
            sea_sale_factor = air_sale_factor
            # The existing bill setting is deliberately reused: Poids means
            # air freight, while Volume means maritime freight.
            is_maritime = line.move_id.primetech_calculation_basis == "volume"
            line.primetech_weight_cost = (
                line.primetech_weight * quantity * (line.move_id.primetech_weight_rate or 0.0)
            )
            line.primetech_volume_cost = (
                line.primetech_volume * quantity * (line.move_id.primetech_volume_rate or 0.0)
            )
            # "Cout.R Final" is the validated final cost for the whole line.
            # It must stay empty (zero) until the user enters the actual cost,
            # exactly like the source grid. CR.poids and CR.volume remain the
            # automatic unit-cost proposals used for analysis.
            line.primetech_final_cost = (
                line.primetech_final_cost_manual
                if line.primetech_final_cost_is_manual
                else 0.0
            )
            line.primetech_cost_by_weight = (
                line.primetech_real_price
                + line.primetech_weight_cost
            )
            line.primetech_cost_by_volume = (
                line.primetech_real_price
                + ((product.volume or 0.0) * (line.move_id.primetech_volume_rate or 0.0))
                if product else line.primetech_real_price
            )
            line.primetech_sale_price_by_weight = line.primetech_cost_by_weight * air_sale_factor
            line.primetech_sale_price_by_volume = line.primetech_cost_by_volume * sea_sale_factor
            # "Prix V Final" starts with the last approved selling price on
            # the product card. The user can override it for this bill; once
            # posted, action_post writes the chosen value back to the product
            # card, which becomes the default on the next supplier bill.
            line.primetech_final_sale_price = (
                line.primetech_final_sale_price_manual
                if line.primetech_final_sale_price_is_manual
                else (product.lst_price if product else 0.0)
            )
            line.primetech_last_final_sale_price = product.lst_price if product else 0.0
