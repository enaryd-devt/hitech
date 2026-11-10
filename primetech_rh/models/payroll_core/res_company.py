# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_journal_id = fields.Many2one(
        "account.journal",
        string="Journal des salaires",
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Journal des écritures générées lors de la validation des bulletins de paie.",
    )
