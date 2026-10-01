# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def primetech_next_reference(self, config_id=False):
        """Return a unique daily reference for the selected POS config."""
        config = self.env["pos.config"].browse(config_id).exists()
        company = config.company_id if config else self.env.company
        sequence_date = fields.Date.context_today(self)
        date_code = sequence_date.strftime("%y%m%d")
        prefix = (config.primetech_order_reference_prefix if config else "COM") or "COM"
        padding = config.primetech_order_sequence_padding if config else 4
        sequence_code = "primetech.pos.order.%s.%s" % (config.id if config else company.id, date_code)
        sequence = self.env["ir.sequence"].sudo().search([
            ("code", "=", sequence_code),
            ("company_id", "=", company.id),
        ], limit=1)
        if not sequence:
            sequence = self.env["ir.sequence"].sudo().create({
                "name": "Commandes POS %s - %s" % (config.display_name if config else company.display_name, date_code),
                "code": sequence_code,
                "prefix": "%s%s" % (prefix.strip(), date_code),
                "padding": padding,
                "implementation": "no_gap",
                "company_id": company.id,
            })
        return sequence.next_by_id(sequence_date=sequence_date)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            reference = vals.get("pos_reference") or ""
            config = self.env["pos.config"].browse(vals.get("config_id")).exists()
            prefix = (config.primetech_order_reference_prefix if config else "COM") or "COM"
            padding = config.primetech_order_sequence_padding if config else 4
            reference_pattern = re.compile(
                r"^%s\d{6}\d{%s}$" % (re.escape(prefix.strip()), padding)
            )
            if not reference_pattern.fullmatch(reference):
                vals["pos_reference"] = self.primetech_next_reference(
                    vals.get("config_id")
                )
        return super().create(vals_list)
