# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_primetech_refresh_invoice_currency_rate(self):
        """Refresh international rates and reload the current supplier bill."""
        self.ensure_one()
        if self.move_type not in ("in_invoice", "in_refund"):
            raise UserError(_("Cette action est disponible uniquement sur une facture fournisseur."))

        result = self.env["res.currency"]._primetech_update_international_rates()
        currency = self.currency_id
        if not currency.active:
            raise UserError(_("La devise sélectionnée n'est pas active."))

        self.invalidate_recordset(["currency_id"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Taux de change actualisé"),
                "message": _("Le taux actuel de %(currency)s a été récupéré (référence du %(date)s).") % {
                    "currency": currency.name,
                    "date": result["date"],
                },
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
