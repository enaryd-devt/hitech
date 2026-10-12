# -*- coding: utf-8 -*-

from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

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
        return result
