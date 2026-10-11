# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """

    _inherit = "hr.contract"
    _description = "Employee Contract"

    struct_id = fields.Many2one("hr.payroll.structure", string="Salary Structure")
    struct_ids = fields.Many2many(
        "hr.payroll.structure",
        "hr_contract_payroll_structure_rel",
        "contract_id",
        "structure_id",
        string="Structures salariales",
        help="Structures cumulées lors du calcul des bulletins de ce contrat.",
    )
    schedule_pay = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("semi-annually", "Semi-annually"),
            ("annually", "Annually"),
            ("weekly", "Weekly"),
            ("bi-weekly", "Bi-weekly"),
            ("bi-monthly", "Bi-monthly"),
        ],
        string="Scheduled Pay",
        index=True,
        default="monthly",
        help="Defines the frequency of the wage payment.",
    )
    resource_calendar_id = fields.Many2one(
        required=True, help="Employee's working schedule."
    )
    payroll_payment_day = fields.Integer(
        string="Jour de paie",
        default=1,
        required=True,
        help=(
            "Jour du mois qui ouvre le cycle de paie de ce contrat. "
            "Pour les mois plus courts, le dernier jour du mois est utilisé."
        ),
    )

    @api.constrains("payroll_payment_day")
    def _check_payroll_payment_day(self):
        for contract in self:
            if not 1 <= contract.payroll_payment_day <= 31:
                raise ValidationError(_("Le jour de paie doit être compris entre 1 et 31."))

    def init(self):
        """Keep existing single-structure contracts compatible after upgrade."""
        self.env.cr.execute(
            """
            INSERT INTO hr_contract_payroll_structure_rel (contract_id, structure_id)
                 SELECT id, struct_id
                   FROM hr_contract
                  WHERE struct_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1
                          FROM hr_contract_payroll_structure_rel relation
                         WHERE relation.contract_id = hr_contract.id
                           AND relation.structure_id = hr_contract.struct_id
                    )
            """
        )

    @api.onchange("struct_id")
    def _onchange_struct_id(self):
        for contract in self:
            if contract.struct_id and contract.struct_id not in contract.struct_ids:
                contract.struct_ids |= contract.struct_id

    @api.onchange("struct_ids")
    def _onchange_struct_ids(self):
        for contract in self:
            if contract.struct_ids and contract.struct_id not in contract.struct_ids:
                contract.struct_id = contract.struct_ids[0]

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
                 hierachy (parent=False first, then first level children and
                 so on) and without duplicates
        """
        # TODO: remove, too simple and not used
        structures = self.struct_id | self.struct_ids
        return structures.get_structure_with_parents()
