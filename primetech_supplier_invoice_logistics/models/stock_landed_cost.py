# -*- coding: utf-8 -*-

from odoo import _, fields, models


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
            lines._compute_primetech_logistics()
            lines.flush_recordset([
                "primetech_final_cost", "primetech_cost_by_weight",
                "primetech_cost_by_volume", "primetech_final_sale_price",
            ])

    def button_validate(self):
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
