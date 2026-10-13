from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    primetech_authorized_employee_ids = fields.Many2many(
        "hr.employee",
        "primetech_pos_authorized_employee_rel",
        "config_id",
        "employee_id",
        string="Employés autorisés à modifier les prix",
        help="Seuls ces employés peuvent modifier le prix d'une ligne de commande au POS.",
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
    primetech_allow_negative_stock_sale = fields.Boolean(
        string="Autoriser la vente en stock négatif",
        default=False,
        help="Autorise uniquement les employés désignés à vendre au-delà du stock disponible de l'entrepôt du POS.",
    )
    primetech_negative_stock_authorized_employee_ids = fields.Many2many(
        "hr.employee",
        "primetech_pos_negative_stock_employee_rel",
        "config_id",
        "employee_id",
        string="Employés autorisés à vendre en négatif",
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
        return fields_list

    def get_limited_products_loading(self, fields):
        """Read POS products with the POS destocking warehouse context.

        Odoo uses this method instead of ``product.product._load_product_with_domain``
        when the catalogue size is limited.  Computed stock fields such as
        ``qty_available`` would otherwise be evaluated over all warehouses.
        """
        warehouse = self.picking_type_id.warehouse_id
        # An empty context would expose global stock.  Use an invalid warehouse
        # id to return zero quantities while the operation type is incomplete.
        return super(PosConfig, self.with_context(warehouse_id=warehouse.id or -1)).get_limited_products_loading(
            fields
        )

    @api.model
    def primetech_get_employee_pos_permissions(self, config_id, employee_id):
        """Return up-to-date POS permissions when an employee logs in."""
        config = self.browse(config_id).exists()
        employee = self.env["hr.employee"].browse(employee_id).exists()
        if not config or not employee:
            return {"role": "cashier", "can_modify_price": False, "can_sell_negative": False}

        visible_employees = self.env["hr.employee"].search(
            config._employee_domain(config.current_user_id.id)
        )
        if employee not in visible_employees:
            return {"role": "cashier", "can_modify_price": False, "can_sell_negative": False}

        if employee.user_id.has_group("primetech_pos_hitech_theme.group_pos_cashier"):
            role = "cashier"
        elif employee.user_id.has_group("primetech_pos_hitech_theme.group_pos_seller"):
            role = "seller"
        else:
            role = "manager" if employee in config.advanced_employee_ids else "cashier"
        return {
            "role": role,
            "can_modify_price": employee in config.primetech_authorized_employee_ids,
            "can_sell_negative": bool(config.primetech_allow_negative_stock_sale)
            and employee in config.primetech_negative_stock_authorized_employee_ids,
        }
