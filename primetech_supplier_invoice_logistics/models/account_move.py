# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    _PRIMETECH_ADDITIONAL_COST_FIELDS = {
        "primetech_additional_logistic_cost",
        "primetech_additional_cost_distribution",
    }

    primetech_proforma_number = fields.Char(
        string="N° proforma", readonly=True, copy=False, index=True,
        help="Référence attribuée lors de la première impression d'une facture en brouillon.",
    )
    primetech_supplier_document_number = fields.Char(
        string="N° facture", compute="_compute_primetech_supplier_document_number",
    )

    @api.depends("name", "state", "move_type", "primetech_proforma_number")
    def _compute_primetech_supplier_document_number(self):
        for move in self:
            if move.move_type == "in_invoice" and move.state == "draft":
                move.primetech_supplier_document_number = move.primetech_proforma_number or "/"
            else:
                move.primetech_supplier_document_number = move.name or "/"

    @api.depends("partner_id", "date", "state", "move_type", "primetech_proforma_number")
    @api.depends_context("input_full_display_name", "primetech_supplier_quote_selector")
    def _compute_display_name(self):
        """Show the RFQ number when selecting a draft supplier bill for an LC."""
        if not self.env.context.get("primetech_supplier_quote_selector"):
            return super()._compute_display_name()
        for move in self:
            if move.move_type == "in_invoice" and move.state == "draft":
                move.display_name = move.primetech_proforma_number or move.name
            else:
                move.display_name = move._get_move_display_name(show_ref=True)
    primetech_amount_paid = fields.Monetary(
        string="Montant réglé", compute="_compute_primetech_amount_paid",
        currency_field="currency_id", readonly=True,
    )

    @api.depends("amount_total", "amount_residual")
    def _compute_primetech_amount_paid(self):
        for move in self:
            move.primetech_amount_paid = max(
                abs(move.amount_total or 0.0) - abs(move.amount_residual or 0.0), 0.0,
            )

    def _primetech_document_reference(self):
        """Return a stable proforma reference for draft invoices.

        The sequence is allocated only once and stored on the invoice so
        repeated printings always show the same proforma number.
        """
        self.ensure_one()
        if self.state != "draft":
            return self.name
        if not self.primetech_proforma_number:
            sequence_code = (
                "primetech.customer.invoice.proforma"
                if self.move_type == "out_invoice"
                else "primetech.supplier.invoice.proforma"
            )
            self.primetech_proforma_number = self.env["ir.sequence"].next_by_code(sequence_code)
        return self.primetech_proforma_number

    def _primetech_payment_state_label(self):
        self.ensure_one()
        labels = {
            "not_paid": _("Non réglée"),
            "in_payment": _("Règlement en cours"),
            "paid": _("Réglée"),
            "partial": _("Partiellement réglée"),
            "reversed": _("Extournée"),
            "invoicing_legacy": _("À régulariser"),
        }
        return labels.get(self.payment_state, self.payment_state or _("Sans règlement"))

    def _primetech_payment_details(self):
        """Payment allocations displayed on the printed invoice."""
        self.ensure_one()
        if self.state != "posted":
            return []
        details = []
        for partial in self.sudo()._get_all_reconciled_invoice_partials():
            line = partial["aml"]
            details.append({
                "date": line.date,
                "reference": line.move_id.name or line.name,
                "journal": line.journal_id.name,
                "collector": line.payment_id.create_uid.name if line.payment_id else line.move_id.create_uid.name,
                "amount": abs(partial["amount"]),
            })
        return details

    def _primetech_report_invoice_lines(self):
        """Invoice article lines only (Odoo 18 uses ``product`` as type)."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(lambda line: line.display_type == "product")

    def _primetech_report_column_visibility(self):
        """Keep the printed table compact by hiding empty optional columns."""
        self.ensure_one()
        lines = self._primetech_report_invoice_lines()
        return {
            "discount": any(line.discount for line in lines),
        }

    def _primetech_sync_global_tax(self):
        """Apply the selected global tax to every article line in draft."""
        for move in self.filtered(lambda item: item.state == "draft" and item.move_type in ("in_invoice", "out_invoice")):
            previous_tax = move.primetech_global_tax_applied_id
            target_tax = move.primetech_global_tax_id if move.primetech_apply_global_tax else self.env["account.tax"]
            for line in move._primetech_report_invoice_lines():
                taxes = line.tax_ids
                if previous_tax:
                    taxes -= previous_tax
                if target_tax:
                    taxes |= target_tax
                line.tax_ids = [(6, 0, taxes.ids)]
            move.with_context(primetech_skip_global_tax_sync=True).write({
                "primetech_global_tax_applied_id": target_tax.id or False,
            })

    @api.onchange("primetech_apply_global_tax", "primetech_global_tax_id")
    def _onchange_primetech_global_tax(self):
        for move in self:
            if move.state == "draft":
                previous_tax = move.primetech_global_tax_applied_id
                target_tax = move.primetech_global_tax_id if move.primetech_apply_global_tax else self.env["account.tax"]
                for line in move._primetech_report_invoice_lines():
                    taxes = line.tax_ids
                    if previous_tax:
                        taxes -= previous_tax
                    if target_tax:
                        taxes |= target_tax
                    line.tax_ids = [(6, 0, taxes.ids)]
                move.primetech_global_tax_applied_id = target_tax

    def _primetech_report_date_in_words(self):
        self.ensure_one()
        date_value = fields.Date.to_date(self.invoice_date or self.date or fields.Date.context_today(self))
        months = (
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        )
        city = self.company_id.city or "Douala"
        return "%s, le %s %s %s" % (city, date_value.day, months[date_value.month - 1].capitalize(), date_value.year)

    def _primetech_report_traceability(self):
        """Readable audit trail for the invoice printout."""
        self.ensure_one()
        pickings = (
            self.primetech_delivery_picking_ids
            if self.move_type == "out_invoice"
            else self.primetech_receipt_picking_ids
        )
        payment_references, payment_accounts, payment_authors = [], [], []
        if self.state == "posted":
            for partial in self.sudo()._get_all_reconciled_invoice_partials():
                line = partial["aml"]
                payment_references.append(line.payment_id.name or line.move_id.name)
                payment_accounts.append(
                    line.payment_id.journal_id.default_account_id.display_name
                    if line.payment_id and line.payment_id.journal_id.default_account_id
                    else line.account_id.display_name
                )
                if line.payment_id:
                    payment_authors.append(line.payment_id.create_uid.name)
        return {
            "pickings": ", ".join(dict.fromkeys(pickings.mapped("name"))) or "—",
            "payment_references": ", ".join(dict.fromkeys(payment_references)) or "—",
            "payment_accounts": ", ".join(dict.fromkeys(payment_accounts)) or "—",
            "payment_authors": ", ".join(dict.fromkeys(payment_authors)) or "—",
            "seller": (self.invoice_user_id.name if self.invoice_user_id else self.create_uid.name) or "—",
        }

    def _primetech_print_invoice(self, expected_type, report_xmlid):
        self.ensure_one()
        if self.move_type != expected_type:
            raise UserError(_("Cette impression n'est disponible que pour le type de facture concerné."))
        self._primetech_document_reference()
        return self.env.ref(report_xmlid).report_action(self)

    def action_print_primetech_customer_invoice(self):
        return self._primetech_print_invoice(
            "out_invoice",
            "primetech_supplier_invoice_logistics.action_report_primetech_customer_invoice",
        )

    def action_print_primetech_supplier_invoice(self):
        return self._primetech_print_invoice(
            "in_invoice",
            "primetech_supplier_invoice_logistics.action_report_primetech_supplier_invoice",
        )

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
    primetech_apply_global_tax = fields.Boolean(string="Appliquer une taxe globale")
    primetech_global_tax_id = fields.Many2one(
        "account.tax", string="Taxe globale", check_company=True,
        domain="[('company_id', 'in', (False, company_id))]",
        help="Cette taxe est appliquée à toutes les lignes d'article de la facture.",
    )
    primetech_global_tax_applied_id = fields.Many2one(
        "account.tax", string="Taxe globale appliquée", copy=False, readonly=True,
    )
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
    primetech_delivery_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Branche / entrepôt", check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    primetech_delivery_picking_type_id = fields.Many2one(
        "stock.picking.type", string="Type de livraison", check_company=True,
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
    )
    primetech_delivery_stock_location_id = fields.Many2one(
        "stock.location", string="Emplacement de stock", check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
    )
    primetech_customer_address = fields.Text(
        string="Adresse client", compute="_compute_primetech_customer_contact",
        readonly=True,
    )
    primetech_customer_phone = fields.Char(
        string="Téléphone", compute="_compute_primetech_customer_contact",
        readonly=True,
    )
    primetech_customer_mobile = fields.Char(
        string="Mobile", compute="_compute_primetech_customer_contact",
        readonly=True,
    )
    primetech_customer_vat = fields.Char(
        string="NIU / N° TVA", compute="_compute_primetech_customer_contact",
        readonly=True,
    )
    primetech_customer_email = fields.Char(
        string="E-mail", compute="_compute_primetech_customer_contact",
        readonly=True,
    )
    primetech_calculation_basis = fields.Selection(
        [("weight", "Poids"), ("volume", "Volume")],
        string="Calcul selon le", default="weight", required=True,
    )
    primetech_weight_rate = fields.Monetary(
        string="Taux poids", currency_field="company_currency_id", digits="Product Price",
        help="Coût logistique par unité de poids, exprimé dans la devise société.",
    )
    primetech_volume_rate = fields.Monetary(
        string="Taux volume", currency_field="company_currency_id", digits="Product Price",
        help="Coût logistique par unité de volume, exprimé dans la devise société.",
    )
    @api.constrains(
        "primetech_weight_rate",
        "primetech_volume_rate",
        "primetech_additional_logistic_cost",
    )
    def _check_primetech_logistic_amounts_non_negative(self):
        for move in self:
            if any(amount < 0 for amount in (
                move.primetech_weight_rate,
                move.primetech_volume_rate,
                move.primetech_additional_logistic_cost,
            )):
                raise ValidationError(_("Les montants logistiques ne peuvent pas être négatifs."))

    primetech_additional_logistic_cost = fields.Monetary(
        string="Coûts logistiques additionnels",
        currency_field="company_currency_id", default=0.0,
        help="Montant total à répartir entre les articles de la facture fournisseur.",
    )
    primetech_additional_cost_distribution = fields.Selection(
        [
            ("equal", "Répartition égale"),
            ("quantity", "Selon la quantité"),
            ("volume", "Selon le volume"),
            ("value", "Selon la valeur"),
        ],
        string="Méthode de répartition", default="equal", required=True,
    )
    primetech_total_additional_logistic_cost = fields.Monetary(
        string="Total coûts logistiques", compute="_compute_primetech_total_additional_cost",
        currency_field="company_currency_id", readonly=True,
    )
    primetech_exchange_rate = fields.Float(
        string="Taux de change", default=1.0, digits="Product Price",
        help="Taux informatif utilisé par les calculs logistiques spécifiques.",
    )
    primetech_display_exchange_rate = fields.Float(
        string="Taux",
        compute="_compute_primetech_display_exchange_rate",
        inverse="_inverse_primetech_display_exchange_rate",
        digits=(16, 6),
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
    primetech_total_margin = fields.Monetary(
        string="Marge totale", compute="_compute_primetech_logistics_totals",
        store=True, currency_field="currency_id",
        help="Marge HT de la facture après application de la réduction éventuelle.",
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
    primetech_receipt_needs_adjustment = fields.Boolean(
        string="Ecart de réception", compute="_compute_primetech_receipt_needs_adjustment",
        help="Indique que les quantités réellement reçues diffèrent de celles de la facture.",
    )
    primetech_delivery_picking_ids = fields.Many2many(
        "stock.picking", "primetech_invoice_delivery_rel", "move_id", "picking_id",
        string="Livraisons liées", copy=False, readonly=True,
    )
    primetech_delivery_picking_count = fields.Integer(
        compute="_compute_primetech_delivery_picking_count", string="Livraisons",
    )
    primetech_return_picking_ids = fields.Many2many(
        "stock.picking", "primetech_invoice_return_rel", "move_id", "picking_id",
        string="Retours liés", copy=False, readonly=True,
    )
    primetech_return_picking_count = fields.Integer(
        compute="_compute_primetech_return_picking_count", string="Retours",
    )
    primetech_credit_note_count = fields.Integer(
        compute="_compute_primetech_credit_note_count", string="Avoirs",
    )
    primetech_landed_cost_count = fields.Integer(
        string="Coûts logistiques", compute="_compute_primetech_landed_cost_count",
    )
    primetech_advance_payment_ids = fields.One2many(
        "account.payment", "primetech_supplier_invoice_id", string="Acomptes",
    )
    primetech_advance_payment_count = fields.Integer(
        compute="_compute_primetech_advance_payment_count", string="Acomptes",
    )

    def _compute_primetech_landed_cost_count(self):
        # These counters can be evaluated while a POS user creates the
        # accounting entry.  Reading a landed cost must not require that user
        # to be an inventory manager; its dedicated actions remain restricted.
        LandedCost = self.env["stock.landed.cost"].sudo()
        for move in self:
            if move.move_type not in ("in_invoice", "in_refund"):
                move.primetech_landed_cost_count = 0
                continue
            move.primetech_landed_cost_count = LandedCost.search_count(
                [("vendor_bill_id", "=", move.id)]
            )

    def _compute_primetech_advance_payment_count(self):
        for move in self:
            move.primetech_advance_payment_count = len(move.primetech_advance_payment_ids)

    def action_primetech_create_landed_cost(self):
        self.ensure_one()
        if self.move_type != "in_invoice":
            raise UserError(_("Cette action est réservée aux factures fournisseurs."))
        if not self.env.user.has_group(
            "primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"
        ):
            raise AccessError(_("Seul le responsable peut créer les coûts logistiques."))
        if self.state != "draft":
            raise UserError(_("Les coûts logistiques doivent être préparés avant la confirmation de la facture."))
        if not self._primetech_supplier_product_lines():
            raise UserError(_("Ajoutez au moins un article et sa quantité avant de créer les coûts logistiques."))
        reference = self._primetech_document_reference()
        landed_cost = self.env["stock.landed.cost"].create({
            "vendor_bill_id": self.id,
            "target_model": "picking",
            "date": self.invoice_date or fields.Date.context_today(self),
            "description": _("Coûts logistiques de la facture fournisseur %s") % reference,
            "company_id": self.company_id.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.landed.cost",
            "res_id": landed_cost.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_view_primetech_landed_costs(self):
        self.ensure_one()
        costs = self.env["stock.landed.cost"].search([("vendor_bill_id", "=", self.id)])
        if len(costs) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "stock.landed.cost",
                "res_id": costs.id, "view_mode": "form", "views": [(False, "form")],
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock_landed_costs.action_stock_landed_cost")
        action["domain"] = [("id", "in", costs.ids)]
        action["context"] = {"default_vendor_bill_id": self.id}
        return action

    def _primetech_supplier_product_lines(self):
        """Lignes d'article éligibles à la répartition des frais."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product") and line.product_id and line.quantity > 0
        )

    def _primetech_additional_cost_weight(self, line, lines):
        """Poids de répartition de frais pour une ligne de facture fournisseur."""
        self.ensure_one()
        method = self.primetech_additional_cost_distribution
        if method == "quantity":
            return line.quantity or 0.0
        if method == "volume":
            return (line.primetech_volume or 0.0) * (line.quantity or 0.0)
        if method == "value":
            date = self.invoice_date or self.date or fields.Date.context_today(self)
            return abs(line.currency_id._convert(
                line.price_subtotal or 0.0,
                self.company_currency_id,
                self.company_id,
                date,
            ))
        return 1.0 if line in lines else 0.0

    def _primetech_additional_cost_share(self, line):
        """Montant de coût additionnel attribué à une ligne, en devise société."""
        self.ensure_one()
        lines = self._primetech_supplier_product_lines()
        amount = self.primetech_additional_logistic_cost or 0.0
        if not amount or line not in lines:
            return 0.0
        denominator = sum(self._primetech_additional_cost_weight(item, lines) for item in lines)
        # Une répartition sans base exploitable retombe proprement à l'égal.
        if not denominator:
            denominator = len(lines)
            numerator = 1.0
        else:
            numerator = self._primetech_additional_cost_weight(line, lines)
        return self.company_currency_id.round(amount * numerator / denominator)

    def _compute_primetech_total_additional_cost(self):
        LandedCost = self.env["stock.landed.cost"].sudo()
        for move in self:
            costs = LandedCost.search([
                ("vendor_bill_id", "=", move.id), ("state", "=", "done"),
            ])
            move.primetech_total_additional_logistic_cost = sum(costs.mapped("amount_total"))

    def action_primetech_add_advance_payment(self):
        """Open the supplier-advance payment assistant."""
        self.ensure_one()
        if self.move_type != "in_invoice" or not self.partner_id:
            raise UserError(_("Sélectionnez d'abord le fournisseur de la facture."))
        reference = self._primetech_document_reference()
        return {
            "type": "ir.actions.act_window",
            "res_model": "primetech.supplier.advance.payment.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_invoice_id": self.id,
                "default_currency_id": self.currency_id.id,
                "default_communication": _("Acompte %s") % reference,
            },
        }

    def action_view_primetech_advance_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action["domain"] = [("primetech_supplier_invoice_id", "=", self.id)]
        action["context"] = {"default_primetech_supplier_invoice_id": self.id}
        return action

    @api.model_create_multi
    def create(self, vals_list):
        # Conserver le comportement existant : les factures fournisseurs
        # créées sans date reçoivent la date du jour.
        today = fields.Date.context_today(self)
        default_move_type = self.env.context.get("default_move_type")
        for vals in vals_list:
            move_type = vals.get("move_type", default_move_type)
            if move_type in ("in_invoice", "in_refund") and not vals.get("invoice_date"):
                vals["invoice_date"] = today
        if (
            any(self._PRIMETECH_ADDITIONAL_COST_FIELDS.intersection(vals) for vals in vals_list)
            and not self.env.user.has_group("primetech_supplier_invoice_logistics.group_supplier_invoice_administrator")
        ):
            raise AccessError(_("Seul le responsable peut définir les coûts logistiques additionnels."))
        return super().create(vals_list)

    def write(self, vals):
        if (
            self._PRIMETECH_ADDITIONAL_COST_FIELDS.intersection(vals)
            and not self.env.user.has_group("primetech_supplier_invoice_logistics.group_supplier_invoice_administrator")
        ):
            raise AccessError(_("Seul le responsable peut modifier les coûts logistiques additionnels."))
        return super().write(vals)

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
        "partner_id", "partner_id.street", "partner_id.street2",
        "partner_id.zip", "partner_id.city", "partner_id.country_id.name",
        "partner_id.phone", "partner_id.mobile", "partner_id.vat", "partner_id.email",
    )
    def _compute_primetech_customer_contact(self):
        for move in self:
            partner = move.partner_id
            if not partner:
                move.primetech_customer_address = False
                move.primetech_customer_phone = False
                move.primetech_customer_mobile = False
                move.primetech_customer_vat = False
                move.primetech_customer_email = False
                continue
            city_line = " ".join(filter(None, [partner.zip, partner.city]))
            address_parts = [
                partner.street, partner.street2, city_line,
                partner.country_id.name if partner.country_id else False,
            ]
            move.primetech_customer_address = ", ".join(filter(None, address_parts))
            move.primetech_customer_phone = partner.phone or partner.mobile
            move.primetech_customer_mobile = (
                partner.mobile if partner.mobile and partner.mobile != partner.phone else False
            )
            move.primetech_customer_vat = partner.vat
            move.primetech_customer_email = partner.email

    @api.depends(
        "invoice_line_ids.quantity", "invoice_line_ids.primetech_weight",
        "invoice_line_ids.primetech_volume", "invoice_line_ids.primetech_final_cost",
        "invoice_line_ids.primetech_constant_cost",
        "invoice_line_ids.primetech_weight_cost",
        "invoice_line_ids.primetech_volume_cost",
        "invoice_line_ids.primetech_cost_by_weight",
        "invoice_line_ids.primetech_cost_by_volume",
        "invoice_line_ids.primetech_sale_cost",
        "primetech_calculation_basis", "amount_untaxed",
        "primetech_apply_discount", "primetech_discount_type", "primetech_discount_value",
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
            if move.move_type in ("out_invoice", "out_refund"):
                move.primetech_total_weight = 0.0
                move.primetech_total_volume = 0.0
                move.primetech_total_weight_volume = 0.0
                total_cost = sum(
                    (line.primetech_sale_cost or 0.0) * (line.quantity or 0.0)
                    for line in lines
                )
                discount = 0.0
                if move.primetech_apply_discount:
                    if move.primetech_discount_type == "percentage":
                        discount = (move.amount_untaxed or 0.0) * (move.primetech_discount_value or 0.0) / 100.0
                    else:
                        discount = move.primetech_discount_value or 0.0
                discount = min(max(discount, 0.0), move.amount_untaxed or 0.0)
                move.primetech_total_cost = total_cost
                move.primetech_total_margin = (move.amount_untaxed or 0.0) - discount - total_cost
                move.primetech_total_constant = 0.0
                continue
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
            automatic_constant_field = (
                "primetech_weight_cost"
                if move.primetech_calculation_basis == "weight"
                else "primetech_volume_cost"
            )
            # The final cost is a unit cost.  The logistics total is therefore
            # the sum of each displayed final cost multiplied by its quantity.
            move.primetech_total_cost = sum(
                (line.primetech_final_cost or 0.0) * (line.quantity or 0.0)
                for line in lines
            )
            move.primetech_total_constant = sum(
                line.primetech_constant_cost or line[automatic_constant_field] or 0.0
                for line in lines
            )
            move.primetech_total_margin = 0.0

    @api.depends("primetech_receipt_picking_ids")
    def _compute_primetech_receipt_picking_count(self):
        for move in self:
            move.primetech_receipt_picking_count = len(move.primetech_receipt_picking_ids)

    @api.depends(
        "move_type", "state", "invoice_line_ids.product_id", "invoice_line_ids.quantity",
        "invoice_line_ids.product_uom_id", "primetech_receipt_picking_ids.state",
        "primetech_receipt_picking_ids.picking_type_id.code",
        "primetech_receipt_picking_ids.move_ids_without_package.state",
        "primetech_receipt_picking_ids.move_ids_without_package.product_id",
        "primetech_receipt_picking_ids.move_ids_without_package.quantity",
        "primetech_receipt_picking_ids.move_ids_without_package.product_uom_qty",
        "primetech_receipt_picking_ids.move_ids_without_package.product_uom",
    )
    def _compute_primetech_receipt_needs_adjustment(self):
        """Show the receipt action only when a supplier receipt has a delta."""
        for move in self:
            move.primetech_receipt_needs_adjustment = False
            if move.move_type != "in_invoice" or move.state != "posted":
                continue
            expected = {}
            for line in move.invoice_line_ids.filtered(
                lambda item: item.display_type in (False, "product")
                and item.product_id and item.quantity > 0
            ):
                product = line.product_id
                quantity = line.product_uom_id._compute_quantity(line.quantity, product.uom_id)
                expected[product.id] = expected.get(product.id, 0.0) + quantity
            actual = {}
            for picking in move._primetech_final_stock_pickings().filtered(
                lambda item: item.state == "done"
            ):
                sign = 1.0 if picking.picking_type_id.code == "incoming" else -1.0
                for stock_move in picking.move_ids_without_package.filtered(
                    lambda item: item.state == "done" and item.product_id
                ):
                    product = stock_move.product_id
                    quantity = stock_move.quantity or stock_move.product_uom_qty
                    quantity = stock_move.product_uom._compute_quantity(quantity, product.uom_id)
                    actual[product.id] = actual.get(product.id, 0.0) + sign * quantity
            for product_id in set(expected) | set(actual):
                product = self.env["product.product"].browse(product_id)
                if not float_is_zero(
                    expected.get(product_id, 0.0) - actual.get(product_id, 0.0),
                    precision_rounding=product.uom_id.rounding,
                ):
                    move.primetech_receipt_needs_adjustment = True
                    break

    @api.depends("primetech_delivery_picking_ids")
    def _compute_primetech_delivery_picking_count(self):
        for move in self:
            move.primetech_delivery_picking_count = len(move.primetech_delivery_picking_ids)

    @api.depends("primetech_return_picking_ids")
    def _compute_primetech_return_picking_count(self):
        for move in self:
            move.primetech_return_picking_count = len(move.primetech_return_picking_ids)

    @api.depends("reversal_move_ids")
    def _compute_primetech_credit_note_count(self):
        for move in self:
            move.primetech_credit_note_count = len(move.reversal_move_ids.filtered(
                lambda reversal: reversal.move_type in ("in_refund", "out_refund")
            ))

    def _primetech_final_stock_pickings(self):
        """Return completed stock documents that define an invoice's net quantity."""
        self.ensure_one()
        if self.move_type == "in_invoice":
            credits = self.reversal_move_ids.filtered(
                lambda move: move.move_type == "in_refund" and move.state == "posted"
            )
            return self.primetech_receipt_picking_ids | credits.primetech_return_picking_ids
        if self.move_type == "out_invoice":
            credits = self.reversal_move_ids.filtered(
                lambda move: move.move_type == "out_refund" and move.state == "posted"
            )
            return self.primetech_delivery_picking_ids | credits.primetech_return_picking_ids
        return self.env["stock.picking"]

    @api.onchange("primetech_warehouse_id")
    def _onchange_primetech_warehouse_id(self):
        for move in self:
            warehouse = move.primetech_warehouse_id
            if warehouse:
                move.primetech_picking_type_id = warehouse.in_type_id
                move.primetech_stock_location_id = warehouse.lot_stock_id

    def _primetech_set_supplier_warehouse_from_location(self, location):
        """Complete a supplier bill header from one destination location."""
        self.ensure_one()
        if (
            self.move_type not in ("in_invoice", "in_refund")
            or self.primetech_warehouse_id
            or not location
        ):
            return False
        warehouse = self.env["stock.warehouse"].search([
            ("company_id", "=", self.company_id.id),
            ("lot_stock_id", "parent_of", location.id),
        ], limit=1)
        if not warehouse:
            return False
        self.primetech_warehouse_id = warehouse
        self.primetech_picking_type_id = warehouse.in_type_id
        self.primetech_stock_location_id = warehouse.lot_stock_id
        return True

    def _primetech_sync_supplier_warehouse_from_lines(self):
        """Use the first line destination when the supplier-bill header is empty."""
        for move in self.filtered(lambda item: item.move_type in ("in_invoice", "in_refund") and not item.primetech_warehouse_id):
            location = move.invoice_line_ids.filtered(
                lambda line: line.display_type in (False, "product") and line.primetech_destination_location_id
            )[:1].primetech_destination_location_id
            move._primetech_set_supplier_warehouse_from_location(location)

    @api.onchange("primetech_delivery_warehouse_id")
    def _onchange_primetech_delivery_warehouse_id(self):
        for move in self:
            warehouse = move.primetech_delivery_warehouse_id
            if warehouse:
                move.primetech_delivery_picking_type_id = warehouse.out_type_id
                move.primetech_delivery_stock_location_id = warehouse.lot_stock_id

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

    @api.onchange("currency_id")
    def _onchange_primetech_convert_invoice_currency(self):
        """Keep a draft invoice economically identical when its currency changes.

        Odoo changes the currency label but does not convert manually entered
        unit prices.  Convert each draft line from its previous currency to
        the newly selected one, then recompute taxes and totals.
        """
        for move in self:
            previous_currency = move._origin.currency_id
            new_currency = move.currency_id
            if (
                move.state != "draft"
                or not previous_currency
                or not new_currency
                or previous_currency == new_currency
            ):
                continue
            conversion_date = move.invoice_date or move.date or fields.Date.context_today(move)
            for line in move.invoice_line_ids.filtered(lambda item: not item.display_type):
                line.price_unit = previous_currency._convert(
                    line.price_unit or 0.0,
                    new_currency,
                    move.company_id,
                    conversion_date,
                )
            if move.primetech_apply_discount and move.primetech_discount_type == "fixed":
                move.primetech_discount_value = previous_currency._convert(
                    move.primetech_discount_value or 0.0,
                    new_currency,
                    move.company_id,
                    conversion_date,
                )
            # In Odoo 18, taxes and totals are dependency-based computed
            # fields; assigning the line prices above triggers their normal
            # onchange recomputation without the removed dynamic-lines API.

    def action_post(self):
        self._primetech_sync_supplier_warehouse_from_lines()
        restricted_moves = self.filtered(
            lambda move: move.move_type == "in_invoice"
            and move.state == "draft"
        )
        if restricted_moves and not self.env.user.has_group(
            "primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"
        ):
            raise UserError(_("Seul l'administrateur des factures fournisseurs logistiques peut confirmer une facture fournisseur."))
        draft_costs = self.env["stock.landed.cost"].search([
            ("vendor_bill_id", "in", restricted_moves.ids), ("state", "=", "draft"),
        ])
        if draft_costs:
            raise UserError(_(
                "Veuillez d'abord confirmer le(s) coût(s) logistique(s) en brouillon lié(s) à cette facture : %s."
            ) % ", ".join(draft_costs.mapped("name")))
        for move in self.filtered(
            lambda item: item.move_type in ("in_invoice", "out_invoice")
            and not (item.move_type == "out_invoice" and item.pos_order_ids)
        ):
            if move.move_type == "in_invoice":
                missing = [
                    label for field, label in (
                        ("primetech_warehouse_id", "Branche / entrepôt"),
                        ("primetech_picking_type_id", "Type de réception"),
                        ("primetech_stock_location_id", "Emplacement de stock"),
                    ) if not move[field]
                ]
            else:
                missing = [
                    label for field, label in (
                        ("primetech_delivery_warehouse_id", "Branche / entrepôt"),
                        ("primetech_delivery_picking_type_id", "Type de livraison"),
                        ("primetech_delivery_stock_location_id", "Emplacement de stock"),
                    ) if not move[field]
                ]
            if missing:
                raise UserError(_(
                    "Vous devez renseigner les informations logistiques avant de confirmer cette facture : %s."
                ) % ", ".join(missing))
        self._primetech_sync_global_tax()
        result = super().action_post()
        # ``write({'state': 'posted'})`` below is the single stock-generation
        # entry point for normal confirmation.  Calling it a second time here
        # used to synchronise an additional receipt using the header's
        # operation type, creating a duplicate of the location-based receipt.
        return result

    def action_primetech_save_supplier_draft(self):
        """Explicit save action for operators preparing a supplier bill.

        The web client saves the form values before invoking an object button;
        reloading then gives the operator an unambiguous saved-draft state.
        """
        self.ensure_one()
        if self.move_type != "in_invoice" or self.state != "draft":
            raise UserError(_("L'enregistrement manuel est uniquement disponible sur une facture fournisseur en brouillon."))
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model_create_multi
    def create(self, vals_list):
        """Also cover invoices imported directly in the posted state."""
        for values in vals_list:
            move_type = values.get("move_type") or self.env.context.get("default_move_type")
            if move_type in ("in_invoice", "in_refund") and not values.get("invoice_date"):
                values["invoice_date"] = fields.Date.context_today(self)
            # A supplier bill receives its internal workflow number as soon as
            # it is saved in draft, so a landed cost and an advance can be
            # linked before accounting confirmation.
            if move_type == "in_invoice" and not values.get("primetech_proforma_number"):
                values["primetech_proforma_number"] = self.env["ir.sequence"].next_by_code(
                    "primetech.supplier.invoice.proforma"
                )
        moves = super().create(vals_list)
        for move in moves.filtered(
            lambda item: item.move_type == "in_invoice" and item.state == "posted"
        ):
            move.sudo()._primetech_create_receipt_picking()
            move.sudo()._primetech_apply_supplier_product_costs()
        for move in moves.filtered(
            lambda item: item.move_type == "out_invoice" and item.state == "posted"
        ):
            move.sudo()._primetech_create_delivery_picking()
        for move in moves.filtered(
            lambda item: item.move_type in ("in_refund", "out_refund") and item.state == "posted"
        ):
            move.sudo()._primetech_create_credit_note_return_picking()
        moves._primetech_sync_global_tax()
        return moves

    def write(self, vals):
        """Cover every posting flow, including custom modules bypassing action_post."""
        result = super().write(vals)
        if (
            not self.env.context.get("primetech_skip_global_tax_sync")
            and {"primetech_apply_global_tax", "primetech_global_tax_id"} & set(vals)
        ):
            self._primetech_sync_global_tax()
        if vals.get("state") == "posted":
            for move in self.filtered(lambda item: item.move_type == "in_invoice"):
                move.sudo()._primetech_create_receipt_picking()
                move.sudo()._primetech_apply_supplier_product_costs()
            for move in self.filtered(lambda item: item.move_type == "out_invoice"):
                move.sudo()._primetech_create_delivery_picking()
            for move in self.filtered(lambda item: item.move_type in ("in_refund", "out_refund")):
                move.sudo()._primetech_create_credit_note_return_picking()
        return result

    def _primetech_create_receipt_picking(self):
        self.ensure_one()
        if self.primetech_receipt_picking_ids:
            return self._primetech_sync_linked_pickings("receipt")
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
        default_destination = self.primetech_stock_location_id or picking_type.default_location_dest_id or picking_type.warehouse_id.lot_stock_id
        if not default_destination:
            raise UserError(_(
                "Configurez un emplacement de destination sur la facture ou "
                "sur le type de réception avant de confirmer la facture."
            ))
        lines_by_destination = {}
        for line in lines:
            destination = line.primetech_destination_location_id or default_destination
            lines_by_destination.setdefault(destination.id, self.env["account.move.line"])
            lines_by_destination[destination.id] |= line
        pickings = self.env["stock.picking"]
        for destination_id, destination_lines in lines_by_destination.items():
            destination = self.env["stock.location"].browse(destination_id)
            destination_picking_type = self._primetech_receipt_picking_type_for_destination(
                destination, fallback_type=picking_type,
            )
            source = (
                destination_picking_type.default_location_src_id
                or self.partner_id.property_stock_supplier
            )
            picking = self.env["stock.picking"].create({
                "picking_type_id": destination_picking_type.id, "move_type": "direct",
                "partner_id": self.partner_id.id, "origin": self.name or self.ref,
                "location_id": source.id, "location_dest_id": destination.id,
                "company_id": self.company_id.id,
                "scheduled_date": self.invoice_date or fields.Datetime.now(),
            })
            # One receipt per destination.  Consolidate duplicate products on
            # that receipt as well, so its lines remain readable even when the
            # supplier bill contains the same article more than once.
            moves_by_product_uom = {}
            for line in destination_lines:
                key = (line.product_id.id, line.product_uom_id.id)
                move_values = moves_by_product_uom.setdefault(key, {
                    "name": line.name or line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": 0.0,
                    "product_uom": line.product_uom_id.id,
                })
                move_values["product_uom_qty"] += line.quantity
            for move_values in moves_by_product_uom.values():
                self.env["stock.move"].create({
                    **move_values, "picking_id": picking.id,
                    "location_id": source.id, "location_dest_id": destination.id,
                    "company_id": self.company_id.id,
                })
            picking.action_confirm()
            picking.primetech_auto_validate_if_fully_available()
            pickings |= picking
        self.primetech_receipt_picking_ids = [(4, picking.id) for picking in pickings]
        return pickings

    def _primetech_receipt_picking_type_for_destination(self, destination, fallback_type=False):
        """Choose the incoming operation configured for ``destination``.

        Each incoming operation owns its receipt sequence.  Selecting it from
        the destination (rather than blindly using the invoice default) makes
        the generated receipt number identify the destination warehouse or
        sub-location.  The invoice operation remains a safe fallback when no
        destination-specific operation has been configured.
        """
        self.ensure_one()
        picking_types = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"), ("company_id", "=", self.company_id.id),
        ])
        destination_path = (destination.parent_path or "").strip("/").split("/")
        matches = []
        for picking_type in picking_types:
            operation_destination = (
                picking_type.default_location_dest_id
                or picking_type.warehouse_id.lot_stock_id
            )
            if not operation_destination:
                continue
            operation_path = (operation_destination.parent_path or "").strip("/").split("/")
            # The operation destination may be the exact location, or a
            # parent warehouse location containing the selected sub-location.
            if destination_path[:len(operation_path)] == operation_path:
                matches.append((len(operation_path), picking_type))
        if matches:
            # The closest matching location is the most specific operation.
            return sorted(matches, key=lambda item: (item[0], item[1].id), reverse=True)[0][1]
        return fallback_type or picking_types[:1]

    def _primetech_apply_supplier_product_costs(self):
        """Apply validated costs and physical measures to the product card."""
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product") and line.product_id
        )
        for line in lines:
            product = line.product_id.with_company(self.company_id)
            # ``standard_price`` is expressed in the company currency, as is
            # the final purchase cost computed on the supplier bill.
            if line.primetech_final_cost > 0:
                product.standard_price = line.primetech_final_cost
            if line.primetech_final_sale_price > 0:
                product.lst_price = line.primetech_final_sale_price
            # A supplier bill is the source of the latest actual packaging
            # data.  Always copy the values held by its line: a future bill
            # will then prefill them again from the article card.  Do not rely
            # on transient onchange flags, which may not exist for imported
            # or programmatically created invoices.
            product.write({
                "weight": line.primetech_weight or 0.0,
                "volume": line.primetech_volume or 0.0,
            })

    def _primetech_stock_invoice_lines(self):
        """Aggregate invoice product lines for stock-transfer synchronisation."""
        self.ensure_one()
        values = {}
        for line in self.invoice_line_ids.filtered(
            lambda item: item.display_type in (False, "product")
            and item.product_id and item.quantity > 0
        ):
            item = values.setdefault(line.product_id.id, {
                "product": line.product_id,
                "uom": line.product_uom_id,
                "quantity": 0.0,
                "name": line.name or line.product_id.display_name,
            })
            item["quantity"] += line.quantity
        return values

    def _primetech_create_stock_adjustment(self, transfer_kind, picking_type, source, destination, lines, suffix):
        """Create and link an additional delivery, receipt, or return picking."""
        self.ensure_one()
        if not lines:
            return self.env["stock.picking"]
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "move_type": "direct",
            "partner_id": self.partner_id.id,
            "origin": "%s — %s" % (self.name or self.ref, suffix),
            "location_id": source.id,
            "location_dest_id": destination.id,
            "company_id": self.company_id.id,
            "scheduled_date": self.invoice_date or fields.Datetime.now(),
        })
        for item in lines.values():
            self.env["stock.move"].create({
                "name": item["name"],
                "product_id": item["product"].id,
                "product_uom_qty": item["quantity"],
                "product_uom": item["uom"].id,
                "picking_id": picking.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
            })
        picking.action_confirm()
        picking.primetech_auto_validate_if_fully_available()
        if transfer_kind == "receipt":
            self.primetech_receipt_picking_ids = [(4, picking.id)]
        else:
            self.primetech_delivery_picking_ids = [(4, picking.id)]
        return picking

    def _primetech_update_open_adjustment(self, transfer_kind, picking_type, source, destination, lines, suffix):
        """Update one open adjustment in place, or create it only when needed."""
        self.ensure_one()
        linked_pickings = (
            self.primetech_receipt_picking_ids if transfer_kind == "receipt"
            else self.primetech_delivery_picking_ids
        )
        candidates = linked_pickings.filtered(
            lambda picking: picking.state not in ("done", "cancel")
            and picking.location_id == source
            and picking.location_dest_id == destination
        )
        if not lines:
            # Preserve the numbered document for audit purposes.  A transfer
            # that is no longer required is cancelled, never deleted, so its
            # sequence and history remain fully traceable.
            for picking in candidates:
                if picking.state == "assigned":
                    picking.move_ids_without_package._do_unreserve()
                picking.action_cancel()
            return self.env["stock.picking"]
        if not candidates:
            return self._primetech_create_stock_adjustment(
                transfer_kind, picking_type, source, destination, lines, suffix,
            )
        picking = candidates[:1]
        if picking.state == "assigned":
            picking.move_ids_without_package._do_unreserve()
        picking.write({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "scheduled_date": self.invoice_date or fields.Datetime.now(),
            "origin": "%s — %s" % (self.name or self.ref, suffix),
        })
        moves_by_product = {}
        for stock_move in picking.move_ids_without_package.filtered(lambda move: move.state != "cancel"):
            moves_by_product.setdefault(stock_move.product_id.id, self.env["stock.move"])
            moves_by_product[stock_move.product_id.id] |= stock_move
        for product_id, item in lines.items():
            moves = moves_by_product.pop(product_id, self.env["stock.move"])
            if moves:
                main_move, extra_moves = moves[:1], moves[1:]
                main_move.write({
                    "name": item["name"], "product_uom_qty": item["quantity"],
                    "product_uom": item["uom"].id, "location_id": source.id,
                    "location_dest_id": destination.id,
                })
                if extra_moves:
                    extra_moves._action_cancel()
            else:
                self.env["stock.move"].create({
                    "name": item["name"], "product_id": item["product"].id,
                    "product_uom_qty": item["quantity"], "product_uom": item["uom"].id,
                    "picking_id": picking.id, "location_id": source.id,
                    "location_dest_id": destination.id, "company_id": self.company_id.id,
                })
        for moves in moves_by_product.values():
            moves._action_cancel()
        picking.action_confirm()
        picking.primetech_auto_validate_if_fully_available()
        # Keep any stale duplicate in the audit trail; never delete a numbered
        # stock document as that would create an unexplained sequence gap.
        for duplicate in candidates[1:]:
            if duplicate.state == "assigned":
                duplicate.move_ids_without_package._do_unreserve()
            duplicate.action_cancel()
        return picking

    def _primetech_sync_linked_pickings(self, transfer_kind):
        """Synchronise editable pickings; create delta or return pickings after validation."""
        self.ensure_one()
        is_receipt = transfer_kind == "receipt"
        pickings = (
            self.primetech_receipt_picking_ids if is_receipt
            else self.primetech_delivery_picking_ids
        )
        picking_type = (
            self.primetech_picking_type_id if is_receipt
            else self.primetech_delivery_picking_type_id
        )
        code = "incoming" if is_receipt else "outgoing"
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([
                ("code", "=", code), ("company_id", "=", self.company_id.id),
            ], limit=1)
        if not picking_type:
            return pickings
        source = (
            (picking_type.default_location_src_id or self.partner_id.property_stock_supplier)
            if is_receipt else
            (self.primetech_delivery_stock_location_id or picking_type.default_location_src_id or picking_type.warehouse_id.lot_stock_id)
        )
        destination = (
            (self.primetech_stock_location_id or picking_type.default_location_dest_id or picking_type.warehouse_id.lot_stock_id)
            if is_receipt else
            (picking_type.default_location_dest_id or self.partner_id.property_stock_customer)
        )
        if not source or not destination:
            raise UserError(_("Configurez les emplacements de stock avant de confirmer la facture."))
        expected = self._primetech_stock_invoice_lines()
        done_pickings = pickings.filtered(lambda picking: picking.state == "done")
        editable = pickings.filtered(lambda picking: picking.state not in ("done", "cancel"))[:1]
        # Before any transfer has been validated, retain and update the first
        # linked picking: it is still the invoice's original full transfer.
        if editable and not done_pickings:
            picking = editable
            if picking.state == "assigned":
                picking.move_ids_without_package._do_unreserve()
            picking.write({
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "scheduled_date": self.invoice_date or fields.Datetime.now(),
            })
            moves_by_product = {}
            for stock_move in picking.move_ids_without_package.filtered(lambda move: move.state != "cancel"):
                moves_by_product.setdefault(stock_move.product_id.id, self.env["stock.move"])
                moves_by_product[stock_move.product_id.id] |= stock_move
            for product_id, item in expected.items():
                moves = moves_by_product.pop(product_id, self.env["stock.move"])
                if moves:
                    main_move, extra_moves = moves[:1], moves[1:]
                    main_move.write({
                        "name": item["name"], "product_uom_qty": item["quantity"],
                        "product_uom": item["uom"].id, "location_id": source.id,
                        "location_dest_id": destination.id,
                    })
                    if extra_moves:
                        extra_moves._action_cancel()
                else:
                    self.env["stock.move"].create({
                        "name": item["name"], "product_id": item["product"].id,
                        "product_uom_qty": item["quantity"], "product_uom": item["uom"].id,
                        "picking_id": picking.id, "location_id": source.id,
                        "location_dest_id": destination.id, "company_id": self.company_id.id,
                    })
            for moves in moves_by_product.values():
                moves._action_cancel()
            picking.action_confirm()
            picking.primetech_auto_validate_if_fully_available()
            return picking

        actual = {}
        for picking in done_pickings:
            sign = 1 if (
                picking.location_id == source and picking.location_dest_id == destination
            ) else -1
            for stock_move in picking.move_ids_without_package:
                quantity = stock_move.quantity or stock_move.product_uom_qty
                actual[stock_move.product_id.id] = actual.get(stock_move.product_id.id, 0.0) + sign * quantity
        additions, returns = {}, {}
        product_ids = set(expected) | set(actual)
        for product_id in product_ids:
            item = expected.get(product_id)
            desired = item["quantity"] if item else 0.0
            delta = desired - actual.get(product_id, 0.0)
            if abs(delta) < 1e-6:
                continue
            if not item:
                stock_move = pickings.filtered(lambda picking: picking.state == "done").move_ids_without_package.filtered(
                    lambda move: move.product_id.id == product_id
                )[:1]
                if not stock_move:
                    continue
                item = {"product": stock_move.product_id, "uom": stock_move.product_uom, "quantity": 0.0, "name": stock_move.name}
            item = dict(item)
            item["quantity"] = abs(delta)
            (additions if delta > 0 else returns)[product_id] = item
        adjustments = self.env["stock.picking"]
        if additions:
            adjustments |= self._primetech_update_open_adjustment(
                transfer_kind, picking_type, source, destination, additions,
                _("Complément de facture"),
            )
        else:
            self._primetech_update_open_adjustment(
                transfer_kind, picking_type, source, destination, {},
                _("Complément de facture"),
            )
        if returns:
            reverse_code = "outgoing" if is_receipt else "incoming"
            return_type = self.env["stock.picking.type"].search([
                ("code", "=", reverse_code), ("company_id", "=", self.company_id.id),
            ], limit=1)
            if not return_type:
                raise UserError(_("Aucun type d'opération de retour n'est configuré."))
            adjustments |= self._primetech_update_open_adjustment(
                transfer_kind, return_type, destination, source, returns,
                _("Retour suite à modification de facture"),
            )
        else:
            reverse_code = "outgoing" if is_receipt else "incoming"
            return_type = self.env["stock.picking.type"].search([
                ("code", "=", reverse_code), ("company_id", "=", self.company_id.id),
            ], limit=1)
            if return_type:
                self._primetech_update_open_adjustment(
                    transfer_kind, return_type, destination, source, {},
                    _("Retour suite à modification de facture"),
                )
        return adjustments or pickings

    def action_create_primetech_receipt(self):
        """Create the receipt complement or return note required by a delta."""
        self.ensure_one()
        if not self.env.user.has_group("primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"):
            raise UserError(_("Seul l'administrateur des factures fournisseurs logistiques peut gérer les réceptions."))
        if self.move_type != "in_invoice" or self.state not in ("draft", "posted"):
            raise UserError(_("La réception peut uniquement être créée pour une facture fournisseur."))
        expected = self._primetech_stock_invoice_lines()
        actual = {}
        for picking in self._primetech_final_stock_pickings().filtered(
            lambda item: item.state == "done"
        ):
            sign = 1.0 if picking.picking_type_id.code == "incoming" else -1.0
            for stock_move in picking.move_ids_without_package.filtered(
                lambda item: item.state == "done" and item.product_id
            ):
                quantity = stock_move.quantity or stock_move.product_uom_qty
                quantity = stock_move.product_uom._compute_quantity(
                    quantity, stock_move.product_id.uom_id,
                )
                actual[stock_move.product_id.id] = actual.get(stock_move.product_id.id, 0.0) + sign * quantity
        additions, returns = {}, {}
        invoice_lines_by_product = {}
        expected_quantities = {}
        for line in self.invoice_line_ids.filtered(
            lambda item: item.display_type in (False, "product") and item.product_id and item.quantity > 0
        ):
            invoice_lines_by_product.setdefault(line.product_id.id, line)
            quantity = line.product_uom_id._compute_quantity(line.quantity, line.product_id.uom_id)
            expected_quantities[line.product_id.id] = expected_quantities.get(line.product_id.id, 0.0) + quantity
        for product_id in set(expected) | set(actual):
            item = expected.get(product_id)
            desired = expected_quantities.get(product_id, 0.0)
            delta = desired - actual.get(product_id, 0.0)
            product = (item or {"product": self.env["product.product"].browse(product_id)})["product"]
            if float_is_zero(delta, precision_rounding=product.uom_id.rounding):
                continue
            if delta > 0:
                item = dict(item)
                item["quantity"] = product.uom_id._compute_quantity(delta, item["uom"])
                additions[product_id] = item
            elif product_id in invoice_lines_by_product:
                item = dict(item)
                item["quantity"] = product.uom_id._compute_quantity(-delta, item["uom"])
                returns[product_id] = item

        if not additions and not returns:
            raise UserError(_("Aucun écart de réception à traiter."))
        picking_type = self.primetech_picking_type_id or self.env["stock.picking.type"].search([
            ("code", "=", "incoming"), ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("Aucun type d'opération de réception n'est configuré."))
        source = picking_type.default_location_src_id or self.partner_id.property_stock_supplier
        destination = self.primetech_stock_location_id or picking_type.default_location_dest_id or picking_type.warehouse_id.lot_stock_id
        if not source or not destination:
            raise UserError(_("Configurez les emplacements de stock avant de traiter l'écart."))
        pickings = self.env["stock.picking"]
        if additions:
            pickings |= self._primetech_update_open_adjustment(
                "receipt", picking_type, source, destination, additions, _("Complément de réception"),
            )
        if returns:
            return_type = self.env["stock.picking.type"].search([
                ("code", "=", "outgoing"), ("company_id", "=", self.company_id.id),
            ], limit=1)
            if not return_type:
                raise UserError(_("Aucun type d'opération de retour n'est configuré."))
            pickings |= self._primetech_update_open_adjustment(
                "receipt", return_type, destination, source, returns, _("Retour de réception"),
            )
        if len(pickings) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "res_id": pickings.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action["domain"] = [("id", "in", pickings.ids)]
        action["context"] = {"create": False}
        return action

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

    def _primetech_create_delivery_picking(self):
        """Create the outgoing delivery linked to one customer invoice."""
        self.ensure_one()
        # A POS invoice already belongs to the delivery created by its POS
        # order.  Link that delivery instead of generating a duplicate one.
        if self.pos_order_ids:
            pos_pickings = self.pos_order_ids.mapped("picking_ids")
            if pos_pickings:
                self.primetech_delivery_picking_ids = [(6, 0, pos_pickings.ids)]
            return pos_pickings
        if self.primetech_delivery_picking_ids:
            return self._primetech_sync_linked_pickings("delivery")
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product")
            and line.product_id and line.quantity > 0
        )
        if not lines:
            return self.env["stock.picking"]
        picking_type = self.primetech_delivery_picking_type_id or self.env["stock.picking.type"].search([
            ("code", "=", "outgoing"), ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            return self.env["stock.picking"]
        source = (
            self.primetech_delivery_stock_location_id
            or picking_type.default_location_src_id
            or picking_type.warehouse_id.lot_stock_id
        )
        destination = (
            picking_type.default_location_dest_id
            or self.partner_id.property_stock_customer
        )
        if not source or not destination:
            raise UserError(_(
                "Configurez un emplacement de départ et de destination sur la facture "
                "ou sur le type de livraison avant de confirmer la facture."
            ))
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "move_type": "direct",
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
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
            })
        picking.action_confirm()
        picking.primetech_auto_validate_if_fully_available()
        self.primetech_delivery_picking_ids = [(4, picking.id)]
        return picking

    def action_create_primetech_delivery(self):
        self.ensure_one()
        if self.move_type != "out_invoice" or self.state not in ("draft", "posted"):
            raise UserError(_("La livraison peut uniquement être créée pour une facture client."))
        self.sudo()._primetech_create_delivery_picking()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_view_primetech_deliveries(self):
        self.ensure_one()
        if len(self.primetech_delivery_picking_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "res_id": self.primetech_delivery_picking_ids.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
                "context": {"create": False},
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action["domain"] = [("id", "in", self.primetech_delivery_picking_ids.ids)]
        action["context"] = {"create": False}
        return action

    def _primetech_create_credit_note_return_picking(self):
        """Create the stock return that is inseparable from a posted credit note."""
        self.ensure_one()
        if self.primetech_return_picking_ids:
            return self.primetech_return_picking_ids
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product")
            and line.product_id and line.quantity > 0
        )
        if not lines:
            return self.env["stock.picking"]
        supplier_return = self.move_type == "in_refund"
        original = self.reversed_entry_id
        original_pickings = (
            original.primetech_receipt_picking_ids if supplier_return
            else original.primetech_delivery_picking_ids
        ) if original else self.env["stock.picking"]
        original_picking = original_pickings.filtered(lambda picking: picking.state != "cancel")[:1]
        return_code = "outgoing" if supplier_return else "incoming"
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", return_code), ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("Configurez un type d'opération de retour avant de valider l'avoir."))
        if original_picking:
            source, destination = original_picking.location_dest_id, original_picking.location_id
        elif supplier_return:
            source = self.primetech_stock_location_id or picking_type.default_location_src_id or picking_type.warehouse_id.lot_stock_id
            destination = picking_type.default_location_dest_id or self.partner_id.property_stock_supplier
        else:
            source = picking_type.default_location_src_id or self.partner_id.property_stock_customer
            destination = self.primetech_delivery_stock_location_id or picking_type.default_location_dest_id or picking_type.warehouse_id.lot_stock_id
        if not source or not destination:
            raise UserError(_("Configurez les emplacements de retour avant de valider l'avoir."))
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
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
            })
        picking.action_confirm()
        picking.primetech_auto_validate_if_fully_available()
        self.primetech_return_picking_ids = [(4, picking.id)]
        return picking

    def action_view_primetech_returns(self):
        self.ensure_one()
        if len(self.primetech_return_picking_ids) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "stock.picking",
                "res_id": self.primetech_return_picking_ids.id, "view_mode": "form",
                "views": [(False, "form")], "target": "current", "context": {"create": False},
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action["domain"] = [("id", "in", self.primetech_return_picking_ids.ids)]
        action["context"] = {"create": False}
        return action

    def action_view_primetech_credit_notes(self):
        self.ensure_one()
        credits = self.reversal_move_ids.filtered(lambda move: move.move_type in ("in_refund", "out_refund"))
        if len(credits) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": credits.id, "view_mode": "form", "views": [(False, "form")],
                "target": "current",
            }
        action_ref = "account.action_move_in_refund_type" if self.move_type == "in_invoice" else "account.action_move_out_refund_type"
        action = self.env["ir.actions.actions"]._for_xml_id(action_ref)
        action["domain"] = [("id", "in", credits.ids)]
        return action

    def button_draft(self):
        if self.filtered(lambda move: move.move_type in ("in_invoice", "out_invoice")) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Seul un administrateur Comptabilité peut remettre une facture en brouillon."))
        return super().button_draft()

    def button_cancel(self):
        if self.filtered(lambda move: move.move_type in ("in_invoice", "out_invoice")) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Seul un administrateur Comptabilité peut annuler une facture."))
        return super().button_cancel()

    def unlink(self):
        for move in self:
            if (
                move.primetech_receipt_picking_ids
                or move.primetech_delivery_picking_ids
                or move.primetech_return_picking_ids
                or move.reversed_entry_id
                or move.reversal_move_ids
            ):
                raise UserError(_("Cette facture est liée à un avoir ou à un mouvement de stock et ne peut pas être supprimée."))
        return super().unlink()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    primetech_quantity_received = fields.Float(
        string="Reçu final", compute="_compute_primetech_stock_quantities",
        digits="Product Unit of Measure", readonly=True,
        help="Quantité nette réellement reçue, après déduction des retours liés aux avoirs.",
    )
    primetech_quantity_delivered = fields.Float(
        string="Livré final", compute="_compute_primetech_stock_quantities",
        digits="Product Unit of Measure", readonly=True,
        help="Quantité nette réellement livrée, après déduction des retours liés aux avoirs.",
    )
    primetech_quantity_returned = fields.Float(
        string="Retourné", compute="_compute_primetech_stock_quantities",
        digits="Product Unit of Measure", readonly=True,
    )
    primetech_receipt_delta_status = fields.Selection(
        [("none", "Conforme"), ("shortage", "Complément à recevoir"), ("surplus", "Retour à effectuer")],
        compute="_compute_primetech_receipt_delta_status", string="Écart de réception",
    )

    @api.depends(
        "move_id.move_type", "move_id.state", "product_id", "quantity", "product_uom_id",
        "move_id.primetech_receipt_picking_ids.state",
        "move_id.primetech_receipt_picking_ids.picking_type_id.code",
        "move_id.primetech_receipt_picking_ids.move_ids_without_package.state",
        "move_id.primetech_receipt_picking_ids.move_ids_without_package.product_id",
        "move_id.primetech_receipt_picking_ids.move_ids_without_package.quantity",
        "move_id.primetech_receipt_picking_ids.move_ids_without_package.product_uom_qty",
        "move_id.primetech_receipt_picking_ids.move_ids_without_package.product_uom",
    )
    def _compute_primetech_receipt_delta_status(self):
        """Colour all invoice lines of an article when its net receipt differs."""
        for line in self:
            line.primetech_receipt_delta_status = "none"
        invoices = self.mapped("move_id").filtered(
            lambda move: move.move_type == "in_invoice" and move.state == "posted"
        )
        for invoice in invoices:
            invoice_lines = invoice.invoice_line_ids.filtered(
                lambda line: line.display_type in (False, "product")
                and line.product_id and line.quantity > 0
            )
            expected = {}
            for invoice_line in invoice_lines:
                product = invoice_line.product_id
                quantity = invoice_line.product_uom_id._compute_quantity(
                    invoice_line.quantity, product.uom_id,
                )
                expected[product.id] = expected.get(product.id, 0.0) + quantity
            actual = {}
            for picking in invoice._primetech_final_stock_pickings().filtered(
                lambda item: item.state == "done"
            ):
                sign = 1.0 if picking.picking_type_id.code == "incoming" else -1.0
                for stock_move in picking.move_ids_without_package.filtered(
                    lambda item: item.state == "done" and item.product_id
                ):
                    product = stock_move.product_id
                    quantity = stock_move.quantity or stock_move.product_uom_qty
                    quantity = stock_move.product_uom._compute_quantity(quantity, product.uom_id)
                    actual[product.id] = actual.get(product.id, 0.0) + sign * quantity
            for invoice_line in invoice_lines:
                product = invoice_line.product_id
                delta = actual.get(product.id, 0.0) - expected.get(product.id, 0.0)
                if float_is_zero(delta, precision_rounding=product.uom_id.rounding):
                    continue
                invoice_line.primetech_receipt_delta_status = (
                    "surplus" if delta > 0 else "shortage"
                )

    def _compute_primetech_stock_quantities(self):
        """Show net completed receipts/deliveries, including linked returns."""
        for line in self:
            line.primetech_quantity_received = 0.0
            line.primetech_quantity_delivered = 0.0
            line.primetech_quantity_returned = 0.0
            if not line.product_id or not line.move_id:
                continue
            invoice = line.move_id
            if invoice.move_type in ("in_refund", "out_refund"):
                returned_quantity = 0.0
                for picking in invoice.primetech_return_picking_ids.filtered(
                    lambda item: item.state == "done"
                ):
                    for stock_move in picking.move_ids_without_package.filtered(
                        lambda item: item.product_id == line.product_id and item.state == "done"
                    ):
                        moved_quantity = stock_move.quantity or stock_move.product_uom_qty
                        if stock_move.product_uom != line.product_uom_id:
                            moved_quantity = stock_move.product_uom._compute_quantity(
                                moved_quantity, line.product_uom_id,
                            )
                        returned_quantity += moved_quantity
                line.primetech_quantity_returned = returned_quantity
                continue
            if invoice.move_type == "in_invoice":
                positive_code = "incoming"
            elif invoice.move_type == "out_invoice":
                positive_code = "outgoing"
            else:
                continue
            pickings = invoice._primetech_final_stock_pickings()
            quantity = 0.0
            for picking in pickings.filtered(lambda item: item.state == "done"):
                sign = 1.0 if picking.picking_type_id.code == positive_code else -1.0
                for stock_move in picking.move_ids_without_package.filtered(
                    lambda item: item.product_id == line.product_id and item.state == "done"
                ):
                    moved_quantity = stock_move.quantity or stock_move.product_uom_qty
                    if stock_move.product_uom != line.product_uom_id:
                        moved_quantity = stock_move.product_uom._compute_quantity(
                            moved_quantity, line.product_uom_id,
                        )
                    quantity += sign * moved_quantity
            if invoice.move_type == "in_invoice":
                line.primetech_quantity_received = quantity
            else:
                line.primetech_quantity_delivered = quantity

    def action_open_primetech_supplier_invoice(self):
        """Open the posted supplier bill from a product purchase-history row."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def _primetech_get_last_supplier_line(self):
        """Return the latest posted supplier line for the same product/company."""
        self.ensure_one()
        if not self.product_id:
            return self.env["account.move.line"]
        return self.search([
            ("id", "!=", self.id),
            ("move_id", "!=", self.move_id.id),
            ("product_id", "=", self.product_id.id),
            ("move_id.move_type", "=", "in_invoice"),
            ("move_id.state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ], order="date desc, id desc", limit=1)

    def _primetech_last_supplier_price_in_invoice_currency(self, previous):
        """Express a historic supplier price in the current bill currency."""
        self.ensure_one()
        if not previous:
            return 0.0
        # In the same currency, preserve the exact unit price entered on the
        # latest supplier invoice.  No conversion or monetary rounding occurs.
        if previous.currency_id == self.currency_id:
            return round(previous.price_unit or 0.0, 3)
        if previous.currency_id == previous.company_currency_id:
            previous_real_price = previous.price_unit or 0.0
        else:
            previous_rate = previous.move_id.invoice_currency_rate or 1.0
            previous_real_price = (previous.price_unit or 0.0) / previous_rate
        # Keep the same thousandth precision as the displayed historic and
        # proposed supplier prices, so all related values use one rounding rule.
        previous_real_price = round(previous_real_price, 3)
        if self.currency_id == self.company_currency_id:
            return round(previous_real_price, 3)
        current_rate = self.move_id.invoice_currency_rate or 1.0
        return round(previous_real_price * current_rate, 3)

    @api.onchange("product_id")
    def _onchange_primetech_supplier_last_price(self):
        """Propose supplier price and physical measures from the product card."""
        for line in self:
            if line.move_id.move_type not in ("in_invoice", "in_refund") or not line.product_id:
                continue
            # Weight and volume are snapshots on the supplier-bill line.  They
            # start from the product card but deliberately remain editable.
            line.primetech_weight = line.product_id.weight or 0.0
            line.primetech_volume = line.product_id.volume or 0.0
            if not line._origin.id:
                line.primetech_final_sale_price = line.product_id.lst_price or 0.0
            previous = line._primetech_get_last_supplier_line()
            if previous:
                line.price_unit = line._primetech_last_supplier_price_in_invoice_currency(previous)

    @api.onchange("primetech_weight")
    def _onchange_primetech_weight_manual_value(self):
        """Keep a weight entered in the invoice grid before recomputing."""
        for line in self:
            line.primetech_weight_manual = line.primetech_weight or 0.0
            line.primetech_weight_is_manual = True
            if line.move_id:
                line.move_id._compute_primetech_logistics_totals()

    @api.onchange("primetech_volume")
    def _onchange_primetech_volume_manual_value(self):
        """Keep a volume entered in the invoice grid before recomputing."""
        for line in self:
            line.primetech_volume_manual = line.primetech_volume or 0.0
            line.primetech_volume_is_manual = True
            if line.move_id:
                line.move_id._compute_primetech_logistics_totals()

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
            line.move_id._compute_primetech_logistics_totals()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product = self.env["product.product"].browse(vals["product_id"]).exists() if vals.get("product_id") else False
            if product:
                vals.setdefault("primetech_weight", product.weight or 0.0)
                vals.setdefault("primetech_volume", product.volume or 0.0)
                vals.setdefault("primetech_final_sale_price", product.lst_price or 0.0)
        lines = super().create(vals_list)
        # A final selling price supplied while a supplier bill line is created
        # must be reflected in the product card as well.  The regular screen
        # flow creates the line first and writes this value afterwards, but
        # imports and API clients can provide it directly at creation time.
        if any(
            {"primetech_final_sale_price", "primetech_final_sale_price_manual",
             "primetech_final_sale_price_is_manual"}.intersection(vals)
            for vals in vals_list
        ):
            lines._primetech_sync_final_sale_price_to_product()
        return lines

    def write(self, vals):
        vals = dict(vals)
        # A computed field with an inverse can be recalculated by another
        # onchange in the same web-client save.  Retain the value explicitly
        # supplied by the user and persist its manual flag after that write.
        # This makes the override deterministic for inline invoice grids.
        final_sale_price = vals.get("primetech_final_sale_price")
        final_sale_price_edited = "primetech_final_sale_price" in vals
        result = super().write(vals)
        if final_sale_price_edited:
            super(AccountMoveLine, self).write({
                "primetech_final_sale_price_manual": final_sale_price or 0.0,
                "primetech_final_sale_price_is_manual": True,
            })
        if "product_id" in vals and not {"primetech_weight", "primetech_volume"}.intersection(vals):
            for line in self.filtered(lambda item: item.product_id):
                # Directly update the snapshots after an article change.  This
                # bypasses this override and cannot overwrite a manual entry.
                super(AccountMoveLine, line).write({
                    "primetech_weight": line.product_id.weight or 0.0,
                    "primetech_volume": line.product_id.volume or 0.0,
                })
        if final_sale_price_edited or {
            "primetech_final_sale_price",
            "primetech_final_sale_price_manual",
            "primetech_final_sale_price_is_manual",
        }.intersection(vals):
            self._primetech_sync_final_sale_price_to_product()
        return result

    def _primetech_sync_final_sale_price_to_product(self):
        """Persist an edited final sale price on the related product.

        This intentionally runs only after ``create``/``write`` succeeds, so
        an onchange or an abandoned invoice cannot change the catalogue.  The
        field itself is limited in the view to the logistics administrators;
        sudo only avoids a missing product-write permission preventing the
        supplier bill from being saved for such an authorised user.
        """
        for line in self:
            if (
                line.move_id.move_type != "in_invoice"
                or not line.product_id
                or line.primetech_final_sale_price <= 0
            ):
                continue
            line.product_id.with_company(line.company_id).sudo().write({
                "lst_price": line.primetech_final_sale_price,
            })

    def unlink(self):
        return super().unlink()

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
    primetech_destination_location_id = fields.Many2one(
        "stock.location", string="Emplacement de destination", check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
        help="Si vide, l'emplacement de destination défini sur la facture est utilisé.",
    )

    @api.onchange("primetech_destination_location_id")
    def _onchange_primetech_destination_location_id(self):
        for line in self:
            line.move_id._primetech_set_supplier_warehouse_from_location(
                line.primetech_destination_location_id
            )
    primetech_weight = fields.Float(
        string="Poids", digits=(16, 6), default=0.0,
    )
    primetech_weight_manual = fields.Float(digits=(16, 6), copy=False)
    primetech_weight_is_manual = fields.Boolean(copy=False)
    primetech_volume = fields.Float(
        string="Volume", digits=(16, 6), default=0.0,
    )
    primetech_volume_manual = fields.Float(digits=(16, 6), copy=False)
    primetech_volume_is_manual = fields.Boolean(copy=False)
    primetech_last_price = fields.Monetary(
        string="Dernier Prix", compute="_compute_primetech_logistics",
        currency_field="currency_id", digits=(16, 3),
    )
    primetech_stock_quantity = fields.Float(
        string="Stock actuel", compute="_compute_primetech_logistics",
        help="Quantité actuellement disponible pour l'article dans Odoo.",
    )
    primetech_last_real_price = fields.Monetary(
        string="Dernier Prix Réel", compute="_compute_primetech_logistics",
        currency_field="company_currency_id", digits=(16, 3),
    )
    primetech_sale_cost = fields.Monetary(
        string="Coût", compute="_compute_primetech_logistics",
        currency_field="currency_id", store=True,
        help="Coût unitaire de l'article pour la facture client.",
    )
    primetech_line_margin = fields.Monetary(
        string="Marge totale", compute="_compute_primetech_logistics",
        currency_field="currency_id", store=True,
        help="Marge hors taxes de la ligne de facture client.",
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
    primetech_additional_logistic_cost = fields.Monetary(
        string="Coût logistique unitaire", compute="_compute_primetech_additional_logistic_cost",
        currency_field="company_currency_id", readonly=True,
        help="Part des coûts logistiques attribuée à une unité de cette ligne.",
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
        string="Prix V Final", default=0.0, currency_field="company_currency_id",
    )
    primetech_final_sale_price_manual = fields.Monetary(currency_field="company_currency_id", copy=False)
    primetech_final_sale_price_is_manual = fields.Boolean(copy=False)
    primetech_sale_price_by_weight = fields.Monetary(
        string="P.V. poids", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_sale_price_by_volume = fields.Monetary(
        string="P.V. volume", compute="_compute_primetech_logistics", currency_field="company_currency_id",
    )
    primetech_proposed_sale_price = fields.Monetary(
        string="Props. PV", compute="_compute_primetech_proposed_sale_price",
        currency_field="company_currency_id", readonly=True,
        help="Proposition de prix de vente calculée à partir du coût de revient final et du taux défini sur l'article.",
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
            line.primetech_final_cost_manual = max(
                (line.primetech_final_cost or 0.0)
                - (line.primetech_additional_logistic_cost or 0.0),
                0.0,
            )
            line.primetech_final_cost_is_manual = True

    def _inverse_primetech_final_sale_price(self):
        for line in self:
            line.primetech_final_sale_price_manual = line.primetech_final_sale_price
            line.primetech_final_sale_price_is_manual = True

    @api.depends("primetech_final_cost", "product_id.primetech_sale_proposal_rate")
    def _compute_primetech_proposed_sale_price(self):
        for line in self:
            rate = line.product_id.primetech_sale_proposal_rate or 0.0
            final_cost = line.primetech_final_cost or 0.0
            line.primetech_proposed_sale_price = final_cost + (final_cost * rate)

    @api.depends(
        "move_id.primetech_additional_logistic_cost",
        "move_id.primetech_additional_cost_distribution",
        "move_id.invoice_line_ids.quantity",
        "move_id.invoice_line_ids.primetech_volume",
        "move_id.invoice_line_ids.price_subtotal",
        "move_id.invoice_line_ids.display_type",
        "move_id.move_type",
    )
    def _compute_primetech_additional_logistic_cost(self):
        # Computed logistics values are also needed by POS-created invoices.
        # Use sudo for this read-only allocation; no landed-cost management
        # permission is thereby granted to the current user.
        LandedCost = self.env["stock.landed.cost"].sudo()
        result = {line.id: 0.0 for line in self}
        invoices = self.mapped("move_id").filtered(
            lambda move: move.move_type in ("in_invoice", "in_refund")
        )
        for invoice in invoices:
            invoice_lines = invoice.invoice_line_ids.filtered(
                lambda line: line.product_id and line.display_type in (False, "product")
            # New invoice lines are represented by ``NewId`` during an
            # onchange.  NewId objects cannot be compared with one another,
            # so use the persisted id when it exists; for unsaved lines the
            # recordset's insertion order remains the tie-breaker.
            ).sorted(
                key=lambda line: (
                    line.sequence,
                    line._origin.id if isinstance(line._origin.id, int) else 0,
                )
            )
            # Draft landed costs are linked directly to the supplier bill,
            # before its receipt exists.  Allocate their validated amount on
            # the bill's own products, quantities and supplier prices.
            direct_costs = LandedCost.search([
                ("vendor_bill_id", "=", invoice.id), ("state", "=", "done"),
            ])
            if direct_costs:
                # The valuation rows are built from the invoice itself and
                # already apply the split method selected on every LC line.
                # Sum them by their exact source invoice line.
                for valuation in direct_costs.mapped("valuation_adjustment_lines").filtered(
                    "primetech_invoice_line_id"
                ):
                    line_id = valuation.primetech_invoice_line_id.id
                    quantity = valuation.primetech_invoice_line_id.quantity or 0.0
                    # The adjustment is a total for the invoice line; the
                    # vendor bill displays logistics as a unit cost.
                    result[line_id] = result.get(line_id, 0.0) + (
                        valuation.additional_landed_cost / quantity if quantity else 0.0
                    )
                # Costs validated before the direct invoice-line link was
                # introduced are kept compatible: distribute their amount by
                # product and quantity instead of leaving the invoice column
                # at zero.
                legacy_valuations = direct_costs.mapped("valuation_adjustment_lines").filtered(
                    lambda valuation: not valuation.primetech_invoice_line_id
                )
                legacy_by_product = {}
                for valuation in legacy_valuations:
                    legacy_by_product[valuation.product_id.id] = (
                        legacy_by_product.get(valuation.product_id.id, 0.0)
                        + (valuation.additional_landed_cost or 0.0)
                    )
                for product_id, amount in legacy_by_product.items():
                    product_lines = invoice_lines.filtered(lambda item: item.product_id.id == product_id)
                    quantity = sum(product_lines.mapped("quantity"))
                    if quantity:
                        for item in product_lines:
                            result[item.id] = result.get(item.id, 0.0) + amount / quantity
                for item in invoice_lines:
                    result[item.id] = invoice.company_currency_id.round(result.get(item.id, 0.0))
                continue
            receipt_moves = invoice.primetech_receipt_picking_ids.filtered(
                lambda picking: picking.picking_type_code == "incoming"
            ).move_ids.filtered(lambda stock_move: stock_move.state != "cancel" and stock_move.quantity)
            costs = LandedCost.search([
                ("picking_ids", "in", receipt_moves.picking_id.ids),
                ("state", "=", "done"),
            ]) if receipt_moves else LandedCost
            valuation_by_move = {}
            for valuation in costs.mapped("valuation_adjustment_lines").filtered(
                lambda valuation: valuation.move_id in receipt_moves
            ):
                valuation_by_move[valuation.move_id.id] = (
                    valuation_by_move.get(valuation.move_id.id, 0.0)
                    + valuation.additional_landed_cost
                )

            # Les mouvements de réception sont créés depuis les lignes de la
            # facture. On consomme leurs quantités dans l'ordre : chaque ligne
            # reçoit ainsi exactement les ajustements calculés par le LC et sa
            # méthode de répartition Odoo (quantité, poids, volume, valeur…).
            moves_by_product = {}
            # An onchange may contain unsaved receipt moves. Their ``id`` is
            # an Odoo ``NewId``, which cannot be compared with another
            # ``NewId``. Keep the insertion order for those temporary moves
            # while retaining the deterministic order of persisted ones.
            for stock_move in receipt_moves.sorted(
                key=lambda item: item.id if isinstance(item.id, int) else 0
            ):
                moves_by_product.setdefault(stock_move.product_id.id, []).append([
                    stock_move.quantity, valuation_by_move.get(stock_move.id, 0.0)
                ])
            for invoice_line in invoice_lines:
                quantity_left = invoice_line.quantity or 0.0
                allocated = 0.0
                for allocation in moves_by_product.get(invoice_line.product_id.id, []):
                    move_quantity, move_cost = allocation
                    if quantity_left <= 0.0 or move_quantity <= 0.0:
                        continue
                    consumed_quantity = min(quantity_left, move_quantity)
                    allocated += move_cost * consumed_quantity / move_quantity
                    allocation[0] -= consumed_quantity
                    allocation[1] -= move_cost * consumed_quantity / move_quantity
                    quantity_left -= consumed_quantity
                # The allocation returned by stock landed costs belongs to
                # the whole invoice line.  The supplier-bill grid and unit
                # cost calculations must expose the cost for one item.
                quantity = invoice_line.quantity or 0.0
                result[invoice_line.id] = (
                    invoice.company_currency_id.round(allocated / quantity)
                    if quantity else 0.0
                )

        for line in self:
            line.primetech_additional_logistic_cost = result.get(line.id, 0.0)

    @api.depends(
        "product_id", "quantity", "price_unit", "primetech_constant_cost",
        "price_subtotal", "product_id.standard_price",
        "product_id.categ_id.primetech_cost_percentage",
        "product_id.categ_id.primetech_sale_percentage",
        "primetech_weight", "primetech_volume",
        "primetech_final_cost_manual", "primetech_final_cost_is_manual",
        "primetech_final_sale_price_manual", "primetech_final_sale_price_is_manual",
        "move_id.primetech_additional_logistic_cost",
        "move_id.primetech_additional_cost_distribution",
        "primetech_additional_logistic_cost",
        "move_id.invoice_currency_rate",
        "currency_id", "company_currency_id",
        "move_id.invoice_date", "discount",
    )
    def _compute_primetech_logistics(self):
        for line in self:
            product = line.product_id
            quantity = line.quantity or 0.0
            # Store the physical measure for one unit.  Totals and freight
            # calculations explicitly multiply it by the invoice quantity.
            line.primetech_stock_quantity = product.qty_available if product else 0.0
            previous = line._primetech_get_last_supplier_line()
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
                previous_real_price = round(previous_real_price, 3)
                line.primetech_last_price = line._primetech_last_supplier_price_in_invoice_currency(previous)
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
            if product and line.currency_id and line.company_currency_id:
                sale_cost = line.company_currency_id._convert(
                    product.standard_price or 0.0,
                    line.currency_id,
                    line.company_id,
                    line.move_id.invoice_date or fields.Date.context_today(line),
                )
            else:
                sale_cost = 0.0
            line.primetech_sale_cost = sale_cost
            line.primetech_line_margin = (
                (line.price_subtotal or 0.0)
                - (sale_cost * quantity)
            )
            # Allocations are exclusively determined by each landed-cost
            # line's split method, using quantity, weight, volume or value
            # recorded on this supplier bill.
            line.primetech_weight_cost = 0.0
            line.primetech_volume_cost = 0.0
            line.primetech_cost_by_weight = line.primetech_real_price
            line.primetech_cost_by_volume = line.primetech_real_price
            line.primetech_final_cost = (
                line.primetech_real_price
                + (line.primetech_additional_logistic_cost or 0.0)
            )
            sale_factor = 1 + (line.primetech_sale_percentage or 0.0) / 100.0
            line.primetech_sale_price_by_weight = line.primetech_final_cost * sale_factor
            line.primetech_sale_price_by_volume = line.primetech_final_cost * sale_factor
            # This is an auditable value entered on the supplier bill.  The
            # product price is only proposed when the row is created; a
            # logistics recomputation must never replace a saved user entry.
            line.primetech_last_final_sale_price = product.lst_price if product else 0.0
