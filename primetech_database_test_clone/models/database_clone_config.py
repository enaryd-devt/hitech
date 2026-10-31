# -*- coding: utf-8 -*-

import os

import pytz

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError, ValidationError

PARAM_PREFIX = "primetech_database_test_clone."

# Values used when nothing has been configured yet.
CONFIG_DEFAULTS = {
    "default_backup_root": lambda: os.path.join(tools.config["data_dir"], "primetech_backups"),
    "default_test_database": lambda: "HITECH_TEST",
    "default_planned_hour": lambda: 2.0,
    "default_timezone": lambda: "Africa/Douala",
    "default_retention_count": lambda: 7,
    "default_parallel_jobs": lambda: 4,
    "running_timeout_hours": lambda: 6,
}
FIELD_TYPES = {
    "default_planned_hour": float,
    "default_retention_count": int,
    "default_parallel_jobs": int,
    "running_timeout_hours": int,
}


def get_config(env, key):
    """Read a module setting, falling back to its default value."""
    value = env["ir.config_parameter"].sudo().get_param(PARAM_PREFIX + key)
    if value in (None, False, ""):
        return CONFIG_DEFAULTS[key]()
    try:
        return FIELD_TYPES.get(key, str)(value)
    except ValueError:
        return CONFIG_DEFAULTS[key]()


class PrimetechDatabaseCloneConfig(models.TransientModel):
    _name = "primetech.database.clone.config"
    _description = "Configuration des sauvegardes et bases de test"

    default_backup_root = fields.Char(
        string="Dossier racine des sauvegardes locales",
        required=True,
        help="Chaque nouvelle planification reçoit son propre sous-dossier de ce dossier.",
    )
    default_test_database = fields.Char(string="Base de test par défaut", required=True)
    default_planned_hour = fields.Float(string="Heure d'exécution par défaut", required=True)
    default_timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in sorted(set(pytz.all_timezones))],
        string="Fuseau horaire par défaut",
        required=True,
    )
    default_retention_count = fields.Integer(string="Sauvegardes conservées par défaut", required=True)
    default_parallel_jobs = fields.Integer(string="Processus parallèles par défaut", required=True)
    running_timeout_hours = fields.Integer(
        string="Délai de déblocage (heures)",
        required=True,
        help="Une exécution toujours « en cours » après ce délai est considérée comme interrompue "
             "(redémarrage du serveur pendant une sauvegarde) et la planification est débloquée.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        for key in CONFIG_DEFAULTS:
            if key in fields_list:
                values[key] = get_config(self.env, key)
        return values

    @api.constrains("default_retention_count", "default_parallel_jobs", "running_timeout_hours", "default_planned_hour")
    def _check_values(self):
        for config in self:
            if config.default_retention_count < 0:
                raise ValidationError(_("Le nombre de sauvegardes conservées ne peut pas être négatif."))
            if not 1 <= config.default_parallel_jobs <= 16:
                raise ValidationError(_("Le nombre de processus parallèles doit être compris entre 1 et 16."))
            if config.running_timeout_hours < 1:
                raise ValidationError(_("Le délai de déblocage doit être d'au moins 1 heure."))
            if not 0 <= config.default_planned_hour < 24:
                raise ValidationError(_("L'heure d'exécution doit être comprise entre 00:00 et 23:59."))

    @api.constrains("default_backup_root")
    def _check_backup_root(self):
        for config in self:
            folder = os.path.abspath(os.path.expanduser(config.default_backup_root))
            filestore_root = os.path.abspath(os.path.join(tools.config["data_dir"], "filestore"))
            if folder == filestore_root or folder.startswith(filestore_root + os.sep):
                raise ValidationError(_("Le dossier des sauvegardes ne peut pas être placé dans le filestore Odoo."))

    @api.constrains("default_test_database")
    def _check_test_database(self):
        for config in self:
            self.env["primetech.database.clone.log"]._validate_target_database(
                self.env.cr.dbname, config.default_test_database
            )

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group("primetech_database_test_clone.group_database_test_clone_manager"):
            raise AccessError(_("Vous n'avez pas accès aux sauvegardes et bases de test."))
        params = self.env["ir.config_parameter"].sudo()
        for key in CONFIG_DEFAULTS:
            params.set_param(PARAM_PREFIX + key, str(self[key]))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Configuration"),
                "message": _("Configuration enregistrée. Elle s'applique aux nouvelles planifications."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
