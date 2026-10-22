from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    pos_partner_balance_amount = fields.Monetary(
        string="Solde partenaire",
        compute="_compute_pos_partner_balance",
    )
    pos_partner_balance_direction = fields.Char(
        string="Situation",
        compute="_compute_pos_partner_balance",
    )
    pos_partner_balance_direction_code = fields.Selection(
        [
            ("partner_owes", "Le partenaire nous doit"),
            ("company_owes", "Nous devons au partenaire"),
            ("settled", "Solde réglé"),
        ],
        compute="_compute_pos_partner_balance",
    )
    pos_partner_balance_amount_display = fields.Char(
        compute="_compute_pos_partner_balance",
    )

    def _get_pos_partner_balance(self):
        """Return the unsigned global customer/supplier balance."""
        self.ensure_one()
        commercial_partner = self.commercial_partner_id
        lines = self.env["account.move.line"].search([
            ("partner_id", "child_of", commercial_partner.id),
            ("company_id", "=", self.env.company.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
        ])
        signed_balance = sum(lines.mapped("amount_residual"))
        if not signed_balance:
            direction, direction_code = _("Solde réglé"), "settled"
        elif signed_balance > 0:
            direction, direction_code = _("Le partenaire nous doit"), "partner_owes"
        else:
            direction, direction_code = _("Nous devons au partenaire"), "company_owes"
        return abs(signed_balance), direction, direction_code

    def _compute_pos_partner_balance(self):
        for partner in self:
            (
                partner.pos_partner_balance_amount,
                partner.pos_partner_balance_direction,
                partner.pos_partner_balance_direction_code,
            ) = partner._get_pos_partner_balance()
            partner.pos_partner_balance_amount_display = "{:,.0f}".format(
                partner.pos_partner_balance_amount
            ).replace(",", " ")
