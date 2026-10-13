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

    @api.model
    def get_groups_by_application(self):
        """Expose the functional reporting roles as one normal select field.

        The standard Odoo heuristic uses checkboxes when peer groups do not
        imply each other.  Reporting roles must remain mutually independent
        (a Sales role must not inherit Accounting), so force a selection only
        for this visible category.
        """
        reporting_category = self.env.ref(
            "primetech_reporting_center.module_category_reporting_center",
            raise_if_not_found=False,
        )
        groups_by_application = super().get_groups_by_application()
        if not reporting_category:
            return groups_by_application
        return [
            (app, "selection", groups.sorted("name"), category_name)
            if app == reporting_category else (app, kind, groups, category_name)
            for app, kind, groups, category_name in groups_by_application
        ]
