# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    replenishment_default_destination_location_id = fields.Many2one(
        "stock.location",
        string="Emplacement de destination par défaut",
        domain=[("usage", "=", "internal")],
        config_parameter="primetech_replenishment_request.default_destination_location_id",
    )
    replenishment_auto_validate_transfers = fields.Boolean(
        string="Valider automatiquement les transferts internes",
        default=True,
        config_parameter="primetech_replenishment_request.auto_validate_transfers",
    )
