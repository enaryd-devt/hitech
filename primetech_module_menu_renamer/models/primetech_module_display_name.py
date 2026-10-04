# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PrimetechModuleDisplayName(models.Model):
    """Persistent display-name overrides for Odoo applications.

    A module update rebuilds ``ir.module.module.shortdesc`` from manifests.
    Keeping overrides in a dedicated model lets us immediately restore the
    business name after that rebuild, including each active translation.
    """

    _name = "primetech.module.display.name"
    _description = "Nom affiché d'un module"
    _rec_name = "module_id"
    _order = "module_id"

    module_id = fields.Many2one(
        "ir.module.module",
        string="Module",
        required=True,
        ondelete="cascade",
        domain="[('state', '=', 'installed')]",
    )
    technical_name = fields.Char(related="module_id.name", string="Nom technique", readonly=True)
    current_name = fields.Char(related="module_id.shortdesc", string="Nom actuel", readonly=True)
    custom_name = fields.Char(string="Nom à afficher", required=True, translate=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("primetech_module_display_name_unique", "unique(module_id)", "Un seul nom personnalisé est autorisé par module."),
    ]

    @api.constrains("custom_name")
    def _check_custom_name(self):
        for record in self:
            if not (record.custom_name or "").strip():
                raise ValidationError(_("Le nom à afficher ne peut pas être vide."))

    def _apply_name(self):
        languages = self.env["res.lang"].sudo().search([("active", "=", True)]).mapped("code")
        for record in self.filtered("active"):
            module = record.module_id.sudo()
            menus = self.env["ir.ui.menu"].sudo().search([
                ("parent_id", "=", False),
                ("web_icon", "=like", "%s,%%" % module.name),
            ])
            # Each translated value is written explicitly. This prevents an
            # existing translation (for example « Inventaire ») from masking
            # the new business name in the application switcher.
            for language in set(languages + ["en_US"]):
                translated_module = module.with_context(lang=language)
                translated_menu = menus.with_context(lang=language)
                translated_module.write({"shortdesc": record.custom_name})
                translated_menu.write({"name": record.custom_name})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._apply_name()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"module_id", "custom_name", "active"} & set(vals):
            self._apply_name()
        return result

    def action_apply(self):
        self._apply_name()
        return {"type": "ir.actions.client", "tag": "reload"}


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def update_list(self):
        result = super().update_list()
        # Reapply all configured names after Odoo rebuilds module metadata
        # from each manifest during an Apps-list update.
        self.env["primetech.module.display.name"].sudo().search([])._apply_name()
        return result
