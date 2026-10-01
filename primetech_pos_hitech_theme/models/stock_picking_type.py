from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    primetech_warehouse_name = fields.Char(
        string="Entrepôt de déstockage",
        related="warehouse_id.name",
        readonly=True,
    )

    def _load_pos_data_fields(self, config_id):
        fields_to_load = super()._load_pos_data_fields(config_id)
        if "primetech_warehouse_name" not in fields_to_load:
            fields_to_load.append("primetech_warehouse_name")
        return fields_to_load
