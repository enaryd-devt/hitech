# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLandedCost(models.Model):
    _inherit = "stock.landed.cost"

    # Compatibilité avec une vue résiduelle de mrp_landed_costs présente dans
    # certaines bases : le module peut être désinstallé alors que sa vue est
    # encore chargée. Le champ reste neutre pour les coûts de réception.
    mrp_production_ids = fields.Many2many(
        "mrp.production", "primetech_landed_cost_mrp_production_rel",
        "landed_cost_id", "production_id", string="Ordres de fabrication",
    )
    primetech_supplier_invoice_count = fields.Integer(
        string="Facture fournisseur", compute="_compute_primetech_links",
    )
    primetech_receipt_count = fields.Integer(
        string="Réceptions", compute="_compute_primetech_links",
    )
    primetech_source_invoice_display = fields.Char(
        string="Facture fournisseur source", compute="_compute_primetech_source_invoice_display",
    )

    @api.depends("vendor_bill_id.name", "vendor_bill_id.state", "vendor_bill_id.primetech_proforma_number")
    def _compute_primetech_source_invoice_display(self):
        for cost in self:
            bill = cost.vendor_bill_id
            cost.primetech_source_invoice_display = (
                bill.primetech_proforma_number if bill and bill.state == "draft"
                else bill.name if bill else False
            )

    def _compute_primetech_links(self):
        for cost in self:
            cost.primetech_supplier_invoice_count = 1 if cost.vendor_bill_id else 0
            cost.primetech_receipt_count = len(cost.picking_ids)

    def _primetech_prepare_costing_methods(self):
        """Make receipt products compatible with standard landed costs.

        Odoo only distributes landed costs on AVCO/FIFO products.  Supplier
        receipts in this workflow may still belong to a category using the
        standard method; switch only those categories to AVCO before the
        calculation/validation, while FIFO categories are left untouched.
        """
        for cost in self:
            moves = cost._get_targeted_move_ids().filtered(
                lambda move: move.state != "cancel" and move.quantity and move.product_id
            )
            categories = moves.filtered(
                lambda move: move.product_id.cost_method not in ("average", "fifo")
            ).mapped("product_id.categ_id")
            if categories:
                categories.with_company(cost.company_id).sudo().write({
                    "property_cost_method": "average",
                })

    def compute_landed_cost(self):
        # Before the bill is confirmed there is intentionally no receipt yet.
        # In that case the supplier bill itself is the allocation source
        # (products, quantities and supplier prices); no stock valuation line
        # can or should be generated at this stage.
        direct_costs = self.filtered("vendor_bill_id")
        if direct_costs:
            AdjustmentLine = self.env["stock.valuation.adjustment.lines"]
            for cost in direct_costs:
                invoice_lines = cost.vendor_bill_id.invoice_line_ids.filtered(
                    lambda line: line.product_id and line.display_type in (False, "product") and line.quantity > 0
                )
                cost.valuation_adjustment_lines.unlink()
                if not invoice_lines:
                    continue
                for cost_line in cost.cost_lines:
                    weights = []
                    for line in invoice_lines:
                        former_cost = line.currency_id._convert(
                            (line.price_unit or 0.0) * (line.quantity or 0.0),
                            cost.company_id.currency_id, cost.company_id,
                            cost.vendor_bill_id.invoice_date or fields.Date.context_today(cost),
                        )
                        weights.append((line, former_cost))
                    if cost_line.split_method == "by_quantity":
                        measures = [line.quantity for line, former_cost in weights]
                    elif cost_line.split_method == "by_weight":
                        measures = [(line.primetech_weight or 0.0) * line.quantity for line, former_cost in weights]
                    elif cost_line.split_method == "by_volume":
                        measures = [(line.primetech_volume or 0.0) * line.quantity for line, former_cost in weights]
                    elif cost_line.split_method == "by_current_cost_price":
                        measures = [former_cost for line, former_cost in weights]
                    else:
                        measures = [1.0] * len(weights)
                    denominator = sum(measures) or len(weights)
                    allocated = []
                    for index, ((line, former_cost), measure) in enumerate(zip(weights, measures)):
                        amount = cost.currency_id.round(cost_line.price_unit * measure / denominator)
                        allocated.append(amount)
                        AdjustmentLine.create({
                            "cost_id": cost.id,
                            "cost_line_id": cost_line.id,
                            "product_id": line.product_id.id,
                            "primetech_invoice_line_id": line.id,
                            "quantity": line.quantity,
                            "weight": (line.primetech_weight or 0.0) * line.quantity,
                            "volume": (line.primetech_volume or 0.0) * line.quantity,
                            "former_cost": former_cost,
                            "additional_landed_cost": amount,
                        })
                    # Keep each additional-cost line exactly balanced despite rounding.
                    difference = cost.currency_id.round(cost_line.price_unit - sum(allocated))
                    if difference:
                        last = cost.valuation_adjustment_lines.filtered(
                            lambda item: item.cost_line_id == cost_line
                        )[-1:]
                        last.additional_landed_cost += difference
            remaining = self - direct_costs
            if not remaining:
                return True
            return super(StockLandedCost, remaining).compute_landed_cost()
        self._primetech_prepare_costing_methods()
        return super().compute_landed_cost()

    def _primetech_refresh_invoice_logistic_costs(self):
        """Persist final costs after Odoo has validated the allocation.

        The allocation column is computed from valuation-adjustment lines.
        Those lines are created at landed-cost validation time, outside of the
        dependency graph of the stored final-cost fields on the vendor bill.
        Refresh the affected invoice product lines explicitly.
        """
        invoices = self.mapped("vendor_bill_id") | self.mapped(
            "picking_ids.primetech_supplier_invoice_ids"
        )
        lines = invoices.invoice_line_ids.filtered(lambda line: line.product_id)
        if lines:
            # Direct draft costs do not alter a field on account.move.line,
            # therefore explicitly refresh their allocation before deriving
            # the final unit cost.
            lines._compute_primetech_additional_logistic_cost()
            lines._compute_primetech_logistics()
            lines.flush_recordset([
                "primetech_final_cost", "primetech_cost_by_weight",
                "primetech_cost_by_volume", "primetech_final_sale_price",
            ])

    def _primetech_post_direct_cost_accounting_entries(self):
        """Post accounting entries for costs allocated from a draft vendor bill.

        Standard landed-cost posting relies on stock moves.  In the supplier
        invoice workflow, the allocation is deliberately prepared before the
        receipt exists, so those adjustment lines have no stock move and the
        standard method creates no journal entry.  Each allocated amount is
        therefore debited to the product valuation account (or its expense
        account for manual valuation) and credited to the configured cost-line
        account.
        """
        Move = self.env["account.move"]
        for cost in self:
            if cost.account_move_id:
                continue
            line_values = []
            for adjustment in cost.valuation_adjustment_lines:
                amount = adjustment.additional_landed_cost
                if cost.currency_id.is_zero(amount):
                    continue
                accounts = adjustment.product_id.product_tmpl_id.get_product_accounts()
                debit_account = (
                    accounts.get("stock_valuation")
                    if adjustment.product_id.valuation == "real_time"
                    else accounts.get("expense")
                )
                credit_account = adjustment.cost_line_id.account_id
                if not debit_account or not credit_account:
                    raise UserError(_(
                        "Configurez les comptes de valorisation ou de charge de l'article %s."
                    ) % adjustment.product_id.display_name)
                base_values = {
                    "name": adjustment.name or cost.name,
                    "product_id": adjustment.product_id.id,
                    "quantity": 0,
                }
                debit_values = dict(base_values, account_id=debit_account.id)
                credit_values = dict(base_values, account_id=credit_account.id)
                if amount > 0:
                    debit_values["debit"] = amount
                    credit_values["credit"] = amount
                else:
                    debit_values["credit"] = -amount
                    credit_values["debit"] = -amount
                line_values.extend([(0, 0, debit_values), (0, 0, credit_values)])
            if not line_values:
                continue
            move = Move.create({
                "move_type": "entry",
                "journal_id": cost.account_journal_id.id,
                "date": cost.date,
                "ref": cost.name,
                "line_ids": line_values,
            })
            move._post()
            cost.account_move_id = move.id

    def button_validate(self):
        missing_accounts = self.mapped("cost_lines").filtered(lambda line: not line.account_id)
        if missing_accounts:
            raise UserError(_(
                "Renseignez le compte comptable de chaque ligne de coût logistique avant validation."
            ))
        direct_costs = self.filtered(
            lambda cost: cost.vendor_bill_id and cost.state == "draft"
        )
        if direct_costs:
            if any(not cost.cost_lines for cost in direct_costs):
                raise UserError(_("Ajoutez au moins une ligne de coût logistique avant validation."))
            # Rebuild the allocations from each cost line's split method just
            # before posting, even if the operator did not click Calculate.
            direct_costs.compute_landed_cost()
            direct_costs._primetech_post_direct_cost_accounting_entries()
            direct_costs.write({"state": "done"})
            direct_costs._primetech_refresh_invoice_logistic_costs()
        remaining_costs = self - direct_costs
        if not remaining_costs:
            return True
        self = remaining_costs
        self._primetech_prepare_costing_methods()
        result = super().button_validate()
        self._primetech_refresh_invoice_logistic_costs()
        return result

    def action_view_primetech_vendor_bill(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "account.move",
            "res_id": self.vendor_bill_id.id, "view_mode": "form", "views": [(False, "form")],
        }

    def action_view_primetech_receipts(self):
        self.ensure_one()
        if len(self.picking_ids) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "stock.picking",
                "res_id": self.picking_ids.id, "view_mode": "form", "views": [(False, "form")],
            }
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action

    def action_print_primetech_landed_cost(self):
        return self.env.ref(
            "primetech_supplier_invoice_logistics.action_report_primetech_landed_cost"
        ).report_action(self)


class StockValuationAdjustmentLine(models.Model):
    _inherit = "stock.valuation.adjustment.lines"

    primetech_invoice_line_id = fields.Many2one(
        "account.move.line", string="Ligne de facture fournisseur", copy=False, readonly=True,
    )
