# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """

    _inherit = "hr.contract"
    _description = "Employee Contract"

    struct_id = fields.Many2one("hr.payroll.structure", string="Salary Structure")
    # Odoo 18's contract form supports several applicable salary structures.
    # Keep the historical struct_id above for the integrated payroll engine
    # and expose the native-compatible field required by the standard view.
    struct_ids = fields.Many2many(
        "hr.payroll.structure",
        "primetech_hr_contract_payroll_structure_rel",
        "contract_id",
        "structure_id",
        string="Salary Structures",
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
    # Field expected by the Odoo 18 contract form.  It is kept on the
    # integrated payroll contract so the standard salary view remains valid
    # even when the standalone payroll addon is not installed.
    payroll_payment_day = fields.Integer(
        string="Payment Day",
        default=1,
        help="Day of the month used for the scheduled salary payment.",
    )
    resource_calendar_id = fields.Many2one(
        required=True, help="Employee's working schedule."
    )

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
                 hierachy (parent=False first, then first level children and
                 so on) and without duplicates
        """
        # TODO: remove, too simple and not used
        return self.struct_id.get_structure_with_parents()
