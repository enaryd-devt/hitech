from odoo import Command, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, values):
        """Make the Reporting role selector replace, not accumulate, roles.

        The standard selector relies on an implication hierarchy.  Reporting
        roles intentionally do not imply each other, so their technical
        permissions must be explicitly replaced when the selected role changes.
        """
        values = dict(values)
        role_ids = {
            self.env.ref("primetech_reporting_center.group_role_menu_dashboard").id,
            self.env.ref("primetech_reporting_center.group_role_menu_accounting").id,
            self.env.ref("primetech_reporting_center.group_role_menu_sales").id,
            self.env.ref("primetech_reporting_center.group_role_menu_purchase").id,
            self.env.ref("primetech_reporting_center.group_role_menu_stock").id,
            self.env.ref("primetech_reporting_center.group_role_menu_hr").id,
        }
        selection_key = next(
            (key for key in values if key.startswith("sel_groups_") and {
                int(group_id) for group_id in key[11:].split("_")
            } == role_ids),
            False,
        )
        if not selection_key:
            return super().write(values)

        selected_role_id = values.pop(selection_key) or False
        role_groups = self.env["res.groups"].browse(list(role_ids))
        groups_to_remove = role_groups | role_groups.trans_implied_ids
        result = True
        for user in self:
            groups = user.groups_id - groups_to_remove
            if selected_role_id:
                selected_role = self.env["res.groups"].browse(selected_role_id)
                groups |= selected_role | selected_role.trans_implied_ids
            user_values = dict(values, groups_id=[Command.set(groups.ids)])
            result = super(ResUsers, user).write(user_values) and result
        return result
