from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_primetech_authorization_code = fields.Char(
        related="pos_config_id.primetech_authorization_code",
        readonly=False,
        string="Code d'autorisation des baisses de prix",
    )
    pos_primetech_authorized_employee_ids = fields.Many2many(
        related="pos_config_id.primetech_authorized_employee_ids",
        readonly=False,
        string="Employés autorisés sans code pour les baisses de prix",
    )
    pos_primetech_stock_warning_level = fields.Float(
        related="pos_config_id.primetech_stock_warning_level",
        readonly=False,
        string="Seuil d'alerte",
    )
    pos_primetech_stock_critical_level = fields.Float(
        related="pos_config_id.primetech_stock_critical_level",
        readonly=False,
        string="Seuil critique",
    )
    pos_primetech_order_reference_prefix = fields.Char(
        related="pos_config_id.primetech_order_reference_prefix",
        readonly=False,
        string="Préfixe des commandes",
    )
    pos_primetech_order_sequence_padding = fields.Integer(
        related="pos_config_id.primetech_order_sequence_padding",
        readonly=False,
        string="Chiffres de la séquence",
    )
