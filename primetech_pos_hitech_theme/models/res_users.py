from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _load_pos_data(self, data):
        """Expose the seller role to the POS client without exposing groups."""
        result = super()._load_pos_data(data)
        if self.env.user.has_group("primetech_pos_hitech_theme.group_pos_cashier"):
            for user in result["data"]:
                user["role"] = "cashier"
        elif self.env.user.has_group("primetech_pos_hitech_theme.group_pos_seller"):
            for user in result["data"]:
                user["role"] = "seller"
        return result
