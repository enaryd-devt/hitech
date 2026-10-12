# -*- coding: utf-8 -*-
from odoo import fields, models


class CancelReplenishmentRequestWizard(models.TransientModel):
    _name = "cancel.replenishment.request.wizard"
    _description = "Annuler la demande de réapprovisionnement"

    reason = fields.Text(required=True)

    def action_cancel_request(self):
        requests = self.env["replenishment.request"].browse(self.env.context.get("active_ids", []))
        for wizard in self:
            requests.message_post(body=wizard.reason)
            requests.action_cancel()
        return {"type": "ir.actions.act_window_close"}
