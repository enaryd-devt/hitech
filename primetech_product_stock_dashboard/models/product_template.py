# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def check_access_rights(self, operation, raise_exception=True):
        """Make the product-management checkbox authoritative for articles.

        Users without Odoo's product manager right keep read access, but the
        client must not offer create/edit/delete actions and RPC calls must be
        rejected as well.
        """
        if (
            operation in ("create", "write", "unlink")
            and not self.env.is_superuser()
            and not self.env.user.has_group("product.group_product_manager")
            and not self.env.user.has_group("stock.group_stock_manager")
        ):
            if raise_exception:
                raise AccessError(_(
                    "Vous avez un accès en lecture seule aux articles. "
                    "Activez le droit de création d'article sur votre utilisateur "
                    "pour pouvoir les créer ou les modifier."
                ))
            return False
        return super().check_access_rights(operation, raise_exception=raise_exception)

    @api.model
    def _default_primetech_stock_alert_qty(self):
        return float(self.env["ir.config_parameter"].sudo().get_param(
            "primetech_product_stock_dashboard.default_alert_qty", "0"
        ))

    @api.model
    def _default_primetech_optimal_stock_qty(self):
        return float(self.env["ir.config_parameter"].sudo().get_param(
            "primetech_product_stock_dashboard.default_optimal_qty", "0"
        ))

    primetech_stock_alert_qty = fields.Float(
        string="Quantité d'alerte",
        default=_default_primetech_stock_alert_qty,
        help="Le stock est affiché en alerte lorsque la quantité disponible atteint ce seuil.",
    )
    primetech_optimal_stock_qty = fields.Float(
        string="Quantité optimale",
        default=_default_primetech_optimal_stock_qty,
        help="Niveau de stock cible utilisé par les jauges du tableau Kanban.",
    )
    primetech_stock_alert_qty_is_manual = fields.Boolean(default=False, copy=False)
    primetech_optimal_stock_qty_is_manual = fields.Boolean(default=False, copy=False)
    primetech_stock_level = fields.Selection(
        [("critical", "Critique"), ("warning", "À surveiller"), ("healthy", "Satisfaisant")],
        string="Niveau de stock",
        compute="_compute_primetech_stock_indicators",
    )
    primetech_stock_ratio = fields.Float(
        string="Taux de stock",
        compute="_compute_primetech_stock_indicators",
    )
    primetech_forecast_ratio = fields.Float(
        string="Taux de stock prévu",
        compute="_compute_primetech_stock_indicators",
    )

    primetech_stock_availability_html = fields.Html(
        compute="_compute_primetech_stock_availability",
        compute_sudo=True,
        sanitize=False,
        readonly=True,
    )

    def write(self, vals):
        """Keep track of thresholds intentionally adjusted on an article.

        Global settings only update articles that still use the default values.
        The context flag is used exclusively by the settings propagation.
        """
        self.check_access_rights("write")
        if not self.env.context.get("primetech_stock_global_update"):
            vals = dict(vals)
            if "primetech_stock_alert_qty" in vals:
                vals["primetech_stock_alert_qty_is_manual"] = True
            if "primetech_optimal_stock_qty" in vals:
                vals["primetech_optimal_stock_qty_is_manual"] = True
        return super().write(vals)

    @api.depends(
        "is_storable",
        "qty_available",
        "virtual_available",
        "primetech_stock_alert_qty",
        "primetech_optimal_stock_qty",
    )
    def _compute_primetech_stock_indicators(self):
        for product in self:
            # Services and consumables that do not track inventory must never
            # be classified as low stock simply because their quantity is 0.
            if not product.is_storable:
                product.primetech_stock_level = False
                product.primetech_stock_ratio = 0.0
                product.primetech_forecast_ratio = 0.0
                continue
            available = product.qty_available or 0.0
            optimal = product.primetech_optimal_stock_qty or 0.0
            alert = product.primetech_stock_alert_qty or 0.0
            if available <= 0:
                product.primetech_stock_level = "critical"
            elif available <= alert:
                product.primetech_stock_level = "warning"
            else:
                product.primetech_stock_level = "healthy"
            product.primetech_stock_ratio = min(max((available / optimal * 100.0) if optimal else 0.0, 0.0), 100.0)
            forecast = product.virtual_available or 0.0
            product.primetech_forecast_ratio = min(max((forecast / optimal * 100.0) if optimal else 0.0, 0.0), 100.0)

    @api.depends("is_storable", "qty_available", "product_variant_ids")
    def _compute_primetech_stock_availability(self):
        """Display stock on hand minus reserved stock for each internal location."""
        quant_model = self.env["stock.quant"]
        warehouses = self.env["stock.warehouse"].search([])
        for product in self:
            if not product.is_storable or not product.product_variant_ids:
                product.primetech_stock_availability_html = Markup(
                    '<div class="pt-stock-availability-empty">Aucun stock suivi pour cet article.</div>'
                )
                continue

            groups = quant_model.read_group(
                [
                    ("product_id", "in", product.product_variant_ids.ids),
                    ("location_id.usage", "=", "internal"),
                ],
                ["quantity:sum", "reserved_quantity:sum", "location_id"],
                ["location_id"],
                lazy=False,
            )
            location_ids = [group["location_id"][0] for group in groups if group.get("location_id")]
            locations = {location.id: location for location in self.env["stock.location"].browse(location_ids)}
            lines = []
            for group in groups:
                if not group.get("location_id"):
                    continue
                location = locations[group["location_id"][0]]
                warehouse_name = "Sans entrepot"
                for warehouse in warehouses:
                    if location.parent_path.startswith(warehouse.view_location_id.parent_path):
                        warehouse_name = warehouse.name
                        break
                quantity = (group.get("quantity", 0.0) or 0.0) - (group.get("reserved_quantity", 0.0) or 0.0)
                lines.append((warehouse_name, location.complete_name, quantity))

            if not lines:
                product.primetech_stock_availability_html = Markup(
                    '<div class="pt-stock-availability-empty">Aucune disponibilite dans les emplacements internes.</div>'
                )
                continue

            lines.sort(key=lambda line: (line[0].lower(), line[1].lower()))
            rendered_lines = "".join(
                "<div class=\"pt-stock-availability-row\">"
                "<span class=\"pt-stock-availability-place\"><strong>{}</strong><small>{}</small></span>"
                "<span class=\"pt-stock-availability-qty\">{:g}</span></div>".format(
                    escape(warehouse_name), escape(location_name), quantity
                )
                for warehouse_name, location_name, quantity in lines
            )
            product.primetech_stock_availability_html = Markup(
                '<div class="pt-stock-availability">{}</div>'.format(rendered_lines)
            )
