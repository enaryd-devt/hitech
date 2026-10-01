from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    primetech_authorization_code = fields.Char(
        string="Code d'autorisation des baisses de prix",
        help="Code demandé pour vendre un article sous son prix de vente dans le POS.",
    )
    primetech_authorized_employee_ids = fields.Many2many(
        "hr.employee",
        "primetech_pos_authorized_employee_rel",
        "config_id",
        "employee_id",
        string="Employés autorisés sans code",
        help="Ces employés peuvent vendre sous le prix de vente sans saisir le code.",
    )
    primetech_stock_warning_level = fields.Float(
        string="Seuil d'alerte de stock",
        default=10.0,
        help="Le badge passe en orange lorsque le stock disponible est inférieur ou égal à ce seuil.",
    )
    primetech_stock_critical_level = fields.Float(
        string="Seuil critique de stock",
        default=3.0,
        help="Le badge passe en rouge lorsque le stock disponible est inférieur ou égal à ce seuil.",
    )
    primetech_order_reference_prefix = fields.Char(
        string="Préfixe des commandes POS",
        default="COM",
        required=True,
        help="Préfixe propre à cette caisse. Exemple : C1 pour obtenir C12609300001.",
    )
    primetech_order_sequence_padding = fields.Integer(
        string="Nombre de chiffres de la séquence",
        default=4,
        required=True,
        help="Nombre de chiffres du compteur quotidien des commandes.",
    )

    @api.constrains("primetech_stock_warning_level", "primetech_stock_critical_level")
    def _check_primetech_stock_levels(self):
        for config in self:
            if config.primetech_stock_warning_level < 0 or config.primetech_stock_critical_level < 0:
                raise ValidationError(_("Les seuils de stock ne peuvent pas être négatifs."))
            if config.primetech_stock_critical_level > config.primetech_stock_warning_level:
                raise ValidationError(_("Le seuil critique doit être inférieur ou égal au seuil d'alerte."))

    @api.constrains("primetech_order_reference_prefix", "primetech_order_sequence_padding")
    def _check_primetech_order_reference_format(self):
        for config in self:
            if not (config.primetech_order_reference_prefix or "").strip():
                raise ValidationError(_("Le préfixe des commandes POS est obligatoire."))
            if not 1 <= config.primetech_order_sequence_padding <= 8:
                raise ValidationError(_("La séquence des commandes POS doit comporter entre 1 et 8 chiffres."))

    def _load_pos_data_fields(self, config_id):
        # Some local POS extensions inherit the generic load mixin directly;
        # in that case ``super`` returns an empty list although the POS client
        # requires its configuration fields (use_pricelist, currency, etc.).
        # Loading the complete configuration is safe here: it is one record
        # and keeps the POS bootstrap resilient to the installed extensions.
        fields_list = list(self._fields)
        if "primetech_authorization_code" not in fields_list:
            fields_list.append("primetech_authorization_code")
        return fields_list
