from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_primetech_authorized_employee_ids = fields.Many2many(
        related="pos_config_id.primetech_authorized_employee_ids",
        readonly=False,
        string="Employés autorisés à modifier les prix",
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
    pos_primetech_allow_negative_stock_sale = fields.Boolean(
        related="pos_config_id.primetech_allow_negative_stock_sale",
        readonly=False,
        string="Autoriser la vente en stock négatif",
    )
    pos_primetech_negative_stock_authorized_employee_ids = fields.Many2many(
        related="pos_config_id.primetech_negative_stock_authorized_employee_ids",
        readonly=False,
        string="Employés autorisés à vendre en négatif",
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
