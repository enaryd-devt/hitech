from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    primetech_mobile_money_type = fields.Selection(
        [
            ("other", "Autre"),
            ("cash", "Espèces"),
            ("orange", "Orange Money"),
            ("momo", "MTN MoMo"),
        ],
        string="Type pour transaction Mobile Money",
        default="other",
        required=True,
        help="Identifie la méthode utilisée pour les transferts entre espèces, Orange Money et MTN MoMo.",
    )
