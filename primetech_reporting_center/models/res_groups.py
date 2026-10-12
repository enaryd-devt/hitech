# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.osv import expression


class ResGroups(models.Model):
    _inherit = "res.groups"

    @api.model
    def get_application_groups(self, domain=None):
        """Keep implementation groups out of the standard user access form.

        Odoo rebuilds that form from every application group.  Setting a
        category as invisible alone therefore does not hide its groups.
        """
        technical_category = self.env.ref(
            "primetech_reporting_center.module_category_reporting_center_technical",
            raise_if_not_found=False,
        )
        if technical_category:
            domain = expression.AND([
                domain or [],
                [("category_id", "!=", technical_category.id)],
            ])
        return super().get_application_groups(domain)
