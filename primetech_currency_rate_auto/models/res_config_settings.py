# -*- coding: utf-8 -*-

from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    primetech_currency_rate_auto_enabled = fields.Boolean(
        string="Mise à jour automatique des devises",
        config_parameter="primetech_currency_rate_auto.enabled",
        default=True,
    )

    def action_primetech_update_currency_rates(self):
        result = self.env["res.currency"]._primetech_update_international_rates()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Taux de change mis à jour"),
                "message": _("%(count)s devise(s) actives ont été mises à jour avec les taux du %(date)s.") % {
                    "count": result["updated"], "date": result["date"],
                },
                "type": "success",
                "sticky": False,
            },
        }
