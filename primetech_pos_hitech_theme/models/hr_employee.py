# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    primetech_pos_can_view_stock_quantities = fields.Boolean(
        string="Accès aux quantités au POS",
        default=False,
        help="Autorise ce caissier POS à consulter les quantités, y compris depuis les informations produit.",
    )
    primetech_is_pos_cashier = fields.Boolean(compute="_compute_primetech_is_pos_cashier")

    @api.depends("user_id", "user_id.groups_id")
    def _compute_primetech_is_pos_cashier(self):
        cashier_group = self.env.ref("primetech_pos_hitech_theme.group_pos_cashier", raise_if_not_found=False)
        for employee in self:
            employee.primetech_is_pos_cashier = bool(
                cashier_group and employee.user_id and cashier_group in employee.user_id.groups_id
            )

    def _load_pos_data(self, data):
        """Expose Primetech POS roles on the employee selected in pos_hr."""
        result = super()._load_pos_data(data)
        employees = self.browse([item["id"] for item in result["data"]]).exists()
        roles_by_employee = {}
        for employee in employees:
            if employee.user_id.has_group("primetech_pos_hitech_theme.group_pos_cashier"):
                roles_by_employee[employee.id] = "cashier"
            elif employee.user_id.has_group("primetech_pos_hitech_theme.group_pos_seller"):
                roles_by_employee[employee.id] = "seller"
        for item in result["data"]:
            if item["id"] in roles_by_employee:
                item["_role"] = roles_by_employee[item["id"]]
                item["_primetech_can_view_stock_quantities"] = bool(
                    employees.browse(item["id"]).primetech_pos_can_view_stock_quantities
                )
        return result
