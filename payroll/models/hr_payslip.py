# Part of Odoo.  LICENSE file for full copyright and licensing details.

import logging
import math
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from html import escape

import babel
from dateutil.relativedelta import relativedelta
from pytz import timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import format_amount

from .base_browsable import (
    BaseBrowsableObject,
    BrowsableObject,
    InputLine,
    Payslips,
    WorkedDays,
)

_logger = logging.getLogger(__name__)


class ProratedContract:
    """Expose a contract to salary rules with its period-adjusted wage.

    All other attributes and methods remain those of the real contract.  This
    makes existing rules written with ``contract.wage`` automatically use the
    prorated negotiated salary, without requiring users to rewrite them.
    """

    def __init__(self, contract, wage):
        self._contract = contract
        self.wage = wage

    def __getattr__(self, name):
        return getattr(self._contract, name)

    def __getitem__(self, name):
        return self.wage if name == "wage" else self._contract[name]


class HrPayslip(models.Model):
    _name = "hr.payslip"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Payslip"
    _order = "id desc"

    @api.model
    def _default_payment_journal_id(self):
        """Retourne le journal configuré, puis une caisse ou une banque."""
        return self._get_default_payment_journal(self.env.company)

    @api.model
    def _get_default_payment_journal(self, company):
        """Get the configured payroll journal for ``company`` when usable."""
        Journal = self.env["account.journal"]
        configured_id = self.env["ir.config_parameter"].sudo().get_param(
            "payroll.default_payment_journal_id"
        )
        configured_journal = Journal.browse(int(configured_id)) if configured_id else Journal
        if (
            configured_journal
            and configured_journal.company_id == company
            and configured_journal.type in ("cash", "bank")
        ):
            return configured_journal

        company_domain = [("company_id", "=", company.id)]
        return (
            Journal.search(company_domain + [("type", "=", "cash")], limit=1)
            or Journal.search(company_domain + [("type", "=", "bank")], limit=1)
        )

    @api.model
    def _default_salary_account_id(self):
        return self._get_default_salary_account(self.env.company)

    @api.model
    def _get_default_salary_account(self, company):
        configured_id = self.env["ir.config_parameter"].sudo().get_param(
            "payroll.default_salary_account_id"
        )
        account = self.env["account.account"].browse(
            int(configured_id)
        ) if configured_id else self.env["account.account"]
        return account if account and company in account.company_ids else self.env["account.account"]

    struct_id = fields.Many2one(
        "hr.payroll.structure",
        string="Structure principale",
        readonly=False,
        help="Defines the rules that have to be applied to this payslip, "
        "accordingly to the contract chosen. If you let empty the field "
        "contract, this field isn't mandatory anymore and thus the rules "
        "applied will be all the rules set on the structure of all contracts "
        "of the employee valid for the chosen period",
    )
    struct_ids = fields.Many2many(
        "hr.payroll.structure",
        "hr_payslip_structure_rel",
        "payslip_id",
        "structure_id",
        string="Structures salariales",
        help=(
            "Sélectionnez les structures à cumuler sur ce bulletin, par exemple le "
            "salaire brut, les retenues fiscales, les retenues sociales et les "
            "charges patronales. Les règles identiques ne sont calculées qu’une fois."
        ),
    )

    def init(self):
        """Rattache la structure historique au champ unique multi-sélection."""
        self.env.cr.execute(
            """
            INSERT INTO hr_payslip_structure_rel (payslip_id, structure_id)
                 SELECT payslip.id, payslip.struct_id
                   FROM hr_payslip AS payslip
                  WHERE payslip.struct_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1
                          FROM hr_payslip_structure_rel AS relation
                         WHERE relation.payslip_id = payslip.id
                           AND relation.structure_id = payslip.struct_id
                    )
            """
        )

    name = fields.Char(string="Payslip Name", readonly=True)
    number = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        readonly=True,
    )
    date_from = fields.Date(
        readonly=False,
        required=True,
        default=lambda self: fields.Date.to_string(date.today().replace(day=1)),
        tracking=True,
    )
    date_to = fields.Date(
        readonly=False,
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    period_worked_days = fields.Float(
        string="Jours travaillés sur la période",
        compute="_compute_period_worked_time",
        help="Nombre de jours de travail planifiés entre les deux dates du bulletin.",
    )
    period_worked_hours = fields.Float(
        string="Heures travaillées sur la période",
        compute="_compute_period_worked_time",
        help="Nombre d'heures de travail planifiées entre les deux dates du bulletin.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("verify", "Waiting"),
            ("done", "Done"),
            ("cancel", "Rejected"),
        ],
        string="Status",
        index=True,
        readonly=True,
        copy=False,
        default="draft",
        tracking=True,
        help="""* When the payslip is created the status is \'Draft\'
        \n* If the payslip is under verification, the status is \'Waiting\'.
        \n* If the payslip is confirmed then status is set to \'Done\'.
        \n* When user cancel payslip the status is \'Rejected\'.""",
    )
    line_ids = fields.One2many(
        "hr.payslip.line",
        "slip_id",
        string="Payslip Lines",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        readonly=True,
        copy=False,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    net_to_pay = fields.Monetary(
        string="Net à payer",
        compute="_compute_net_to_pay",
        store=True,
        readonly=True,
        currency_field="currency_id",
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Mode de règlement",
        domain=[("type", "in", ("cash", "bank"))],
        default=_default_payment_journal_id,
        check_company=True,
        tracking=True,
        help="Journal de caisse ou de banque utilisé pour régler ce bulletin.",
    )
    salary_account_id = fields.Many2one(
        "account.account",
        string="Compte de salaire",
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        default=_default_salary_account_id,
        tracking=True,
        help="Compte débité lors du paiement du salaire.",
    )
    payment_move_id = fields.Many2one(
        "account.move",
        string="Écriture de paiement",
        readonly=True,
        copy=False,
        check_company=True,
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Paiement",
        readonly=True,
        copy=False,
        check_company=True,
    )
    payment_accounting_date = fields.Date(
        string="Date de comptabilisation",
        related="payment_move_id.date",
        readonly=True,
    )
    worked_days_line_ids = fields.One2many(
        "hr.payslip.worked_days",
        "payslip_id",
        string="Payslip Worked Days",
        copy=True,
        readonly=True,
    )
    input_line_ids = fields.One2many(
        "hr.payslip.input",
        "payslip_id",
        string="Payslip Inputs",
        readonly=True,
    )
    paid = fields.Boolean(
        string="Made Payment Order ? ",
        readonly=True,
        copy=False,
    )
    note = fields.Text(
        string="Internal Note",
        readonly=True,
        tracking=True,
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contract",
        readonly=True,
        tracking=True,
    )
    dynamic_filtered_payslip_lines = fields.One2many(
        "hr.payslip.line",
        compute="_compute_dynamic_filtered_payslip_lines",
    )
    salary_kpi_html = fields.Html(
        string="Synthèse des structures salariales",
        compute="_compute_salary_kpi_html",
        store=True,
        sanitize=False,
        readonly=True,
    )
    credit_note = fields.Boolean(
        readonly=True,
        help="Indicates this payslip has a refund of another",
    )
    payslip_run_id = fields.Many2one(
        "hr.payslip.run",
        string="Payslip Batches",
        readonly=True,
        copy=False,
        tracking=True,
    )
    payslip_count = fields.Integer(
        compute="_compute_payslip_count", string="Payslip Computation Details"
    )
    hide_child_lines = fields.Boolean(default=False)
    hide_invisible_lines = fields.Boolean(
        string="Show only lines that appear on payslip", default=False
    )
    compute_date = fields.Date()
    refunded_id = fields.Many2one(
        "hr.payslip", string="Avoir associé", readonly=True, copy=False
    )
    refund_origin_id = fields.Many2one(
        "hr.payslip",
        string="Bulletin d'origine",
        readonly=True,
        copy=False,
    )
    allow_cancel_payslips = fields.Boolean(
        "Allow Canceling Payslips", compute="_compute_allow_cancel_payslips"
    )
    prevent_compute_on_confirm = fields.Boolean(
        "Prevent Compute on Confirm", compute="_compute_prevent_compute_on_confirm"
    )

    def _compute_allow_cancel_payslips(self):
        self.allow_cancel_payslips = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("payroll.allow_cancel_payslips")
        )

    def _compute_prevent_compute_on_confirm(self):
        self.prevent_compute_on_confirm = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("payroll.prevent_compute_on_confirm")
        )

    @api.depends("line_ids", "hide_child_lines", "hide_invisible_lines")
    def _compute_dynamic_filtered_payslip_lines(self):
        for payslip in self:
            lines = payslip.line_ids
            if payslip.hide_child_lines:
                lines = lines.filtered(lambda line: not line.parent_rule_id)
            if payslip.hide_invisible_lines:
                lines = lines.filtered(lambda line: line.appears_on_payslip)
            payslip.dynamic_filtered_payslip_lines = lines

    @api.depends(
        "line_ids",
        "line_ids.total",
        "line_ids.category_id",
        "line_ids.category_id.name",
        "line_ids.category_id.code",
        "line_ids.sequence",
        "struct_id",
        "struct_ids",
    )
    def _compute_salary_kpi_html(self):
        """Build the salary-calculation KPI cards from the computed rules.

        One card is rendered for every effective salary structure.  Rules are
        attributed to the structure that owns them directly, which keeps the
        summary meaningful when base and complementary structures are combined.
        """
        for payslip in self:
            structures = payslip._get_salary_structures_with_parents()
            if not payslip.line_ids or not structures:
                payslip.salary_kpi_html = (
                    '<div class="alert alert-info mb-3">'
                    'Calculez le bulletin pour afficher la synthèse salariale.'
                    "</div>"
                )
                continue

            currency = payslip.contract_id.currency_id or payslip.company_id.currency_id
            cards = []
            kpi_count = len(structures) + 1  # one additional card for the net
            if kpi_count <= 3:
                card_basis, value_size = 300, "1.55rem"
            elif kpi_count <= 5:
                card_basis, value_size = 230, "1.35rem"
            elif kpi_count <= 8:
                card_basis, value_size = 190, "1.15rem"
            else:
                card_basis, value_size = 165, "1rem"
            for index, structure in enumerate(structures):
                lines = payslip.line_ids.filtered(
                    lambda line, structure=structure: line.salary_rule_id in structure.rule_ids
                )
                gains = sum(lines.filtered(lambda line: line.total > 0).mapped("total"))
                deductions = sum(lines.filtered(lambda line: line.total < 0).mapped("total"))
                net_lines = lines.filtered(
                    lambda line: (line.code or "").upper() in {"NET", "NETPAY"}
                    or (line.category_id.code or "").upper() in {"NET", "NETPAY"}
                )
                result = sum(net_lines.mapped("total")) if net_lines else gains + deductions
                palette = ("primary", "success", "warning", "info", "secondary")[index % 5]
                result_class = "text-danger" if result < 0 else f"text-{palette}"
                cards.append(
                    '<div style="flex:1 1 %dpx; min-width:155px;">'
                    '<div class="card h-100 border-0 shadow-sm bg-light border-start border-4 border-%s">'
                    '<div class="card-body py-3">'
                    '<div class="text-muted text-uppercase small fw-bold">%s</div>'
                    '<div class="%s fw-bold mt-1" style="font-size:%s;">%s</div>'
                    '<div class="small text-muted mt-2">%s&nbsp;·&nbsp;%s</div>'
                    '</div></div></div>'
                    % (
                        card_basis,
                        palette,
                        escape(structure.name),
                        result_class,
                        value_size,
                        escape(format_amount(payslip.env, result, currency)),
                        _("Gains : %s") % escape(format_amount(payslip.env, gains, currency)),
                        _("Retenues : %s") % escape(format_amount(payslip.env, deductions, currency)),
                    )
                )

            net_lines = payslip.line_ids.filtered(
                lambda line: (line.code or "").upper() in {"NET", "NETPAY"}
                or (line.category_id.code or "").upper() in {"NET", "NETPAY"}
            )
            if net_lines:
                net_to_pay = sum(net_lines.mapped("total"))
            else:
                net_to_pay = sum(payslip.line_ids.filtered(
                    lambda line: (line.code or "").upper() not in {"GROSS", "NET", "NETPAY"}
                    and (line.category_id.code or "").upper() not in {"GROSS", "NET", "NETPAY"}
                ).mapped("total"))
            cards.append(
                '<div style="flex:1 1 %dpx; min-width:155px;">'
                '<div class="card h-100 border-0 shadow-sm border-start border-4 border-success bg-success-subtle">'
                '<div class="card-body py-3">'
                '<div class="text-success text-uppercase small fw-bold">%s</div>'
                '<div class="text-success fw-bold mt-1" style="font-size:%s;">%s</div>'
                '<div class="small text-muted mt-2">%s</div>'
                '</div></div></div>'
                % (
                    card_basis,
                    escape(_("Net à payer")),
                    value_size,
                    escape(format_amount(payslip.env, net_to_pay, currency)),
                    escape(_("Montant net du bulletin")),
                )
            )
            payslip.salary_kpi_html = (
                '<div class="mb-2 text-muted small"><strong>Structures appliquées :</strong> %s</div>'
                '<div class="d-flex flex-nowrap gap-3 mb-3" '
                'style="overflow-x:auto; align-items:stretch;">%s</div>'
                % (escape(", ".join(structures.mapped("name"))), "".join(cards))
            )

    @api.depends(
        "line_ids.total",
        "line_ids.code",
        "line_ids.appears_on_payslip",
        "line_ids.report_section",
        "line_ids.category_id",
        "line_ids.category_id.code",
    )
    def _compute_net_to_pay(self):
        """Stored net amount for fast display and sorting in the list view."""
        for payslip in self:
            payslip.net_to_pay = payslip._dashboard_amounts()["net"]

    def _compute_payslip_count(self):
        for payslip in self:
            payslip.payslip_count = len(payslip.line_ids)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        if any(self.filtered(lambda payslip: payslip.date_from > payslip.date_to)):
            raise ValidationError(
                _("Payslip 'Date From' must be earlier than 'Date To'.")
            )

    @api.constrains("employee_id", "date_from", "date_to", "state")
    def _check_period_not_already_paid(self):
        """A partial payment must complement a period, never pay it twice."""
        for payslip in self:
            # A refund is deliberately a reversal of an already paid period.
            if payslip.credit_note or not (
                payslip.employee_id and payslip.date_from and payslip.date_to
            ):
                continue
            duplicate = self.search_count([
                ("id", "!=", payslip.id),
                ("employee_id", "=", payslip.employee_id.id),
                ("state", "!=", "cancel"),
                ("credit_note", "=", False),
                ("date_from", "<=", payslip.date_to),
                ("date_to", ">=", payslip.date_from),
            ])
            if duplicate:
                raise ValidationError(_(
                    "Cette période chevauche déjà un bulletin existant pour cet employé. "
                    "Choisissez uniquement les jours restant à régler."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._compute_name()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"employee_id", "date_from", "date_to"}.intersection(vals):
            self._compute_name()
        return result

    def copy(self, default=None):
        rec = super().copy(default)
        for line in self.input_line_ids:
            line.copy({"payslip_id": rec.id})
        for line in self.line_ids:
            line.copy({"slip_id": rec.id, "input_ids": []})
        return rec

    def action_payslip_draft(self):
        for payslip in self:
            if payslip.paid and not payslip.refunded_id:
                raise UserError(_(
                    "Un bulletin payé ne peut être remis en brouillon qu'après la création de son avoir."
                ))
        return self.write({"state": "draft"})

    def action_reopen_confirmed_payslip(self):
        """Return a confirmed payslip to draft.

        This operation changes a validated payroll document and is therefore
        deliberately reserved for payroll managers.  Accounting extensions
        may override this method to neutralise their accounting entry first.
        """
        if not self.env.user.has_group("payroll.group_payroll_manager"):
            raise AccessError(
                _("Seul un gestionnaire de paie peut remettre un bulletin confirmé en brouillon.")
            )
        confirmed_slips = self.filtered(lambda slip: slip.state == "done")
        if not confirmed_slips:
            raise UserError(_("Seuls les bulletins confirmés peuvent être remis en brouillon."))
        confirmed_slips.write({"state": "draft"})
        return True

    def action_payslip_done(self):
        for payslip in self.filtered(lambda slip: not slip.credit_note):
            payslip._check_payroll_period_availability()
        if (
            not self.env.context.get("without_compute_sheet")
            and not self.prevent_compute_on_confirm
        ):
            self.compute_sheet()
        return self.write({"state": "done"})

    def action_print_payslip(self):
        """Imprime explicitement le bulletin professionnel après validation."""
        self.ensure_one()
        if self.state != "done":
            raise UserError(_("Le bulletin doit être validé avant impression."))
        return self.env.ref("payroll.action_report_payslip").report_action(self)

    def _get_salary_payment_amount(self):
        """Return the net amount actually paid to the employee."""
        self.ensure_one()
        net_codes = {"NET", "NETPAY", "SN", "SAL_NET"}
        net_lines = self.line_ids.filtered(
            lambda line: (line.code or "").upper() in net_codes
        )
        amount = abs(sum(net_lines.mapped("total")))
        return amount or max(self._dashboard_amounts()["net"], 0.0)

    def action_pay_payslip(self):
        """Post the payroll payment against the selected cash/bank journal."""
        for payslip in self:
            if payslip.state != "done":
                raise UserError(_("Le bulletin doit être validé avant paiement."))
            if payslip.paid or payslip.payment_move_id:
                raise UserError(_("Ce bulletin est déjà réglé."))
            if not payslip.salary_account_id:
                raise UserError(_("Sélectionnez le compte de salaire à débiter."))
            if not payslip.payment_journal_id:
                raise UserError(_("Sélectionnez le mode de règlement."))
            payment_method = payslip.payment_journal_id.outbound_payment_method_line_ids[:1]
            if not payment_method:
                raise UserError(_(
                    "Configurez une méthode de paiement sortante sur le journal des salaires."
                ))

            amount = payslip._get_salary_payment_amount()
            if amount <= 0:
                raise UserError(_("Le montant net à payer doit être strictement positif."))

            # Odoo 18 uses the employee work contact; older deployments can
            # still expose a private/home contact instead.
            partner = (
                getattr(payslip.employee_id, "work_contact_id", False)
                or getattr(payslip.employee_id, "address_home_id", False)
                or payslip.employee_id.user_id.partner_id
            )
            payment = self.env["account.payment"].create({
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": partner.id,
                "amount": amount,
                "currency_id": payslip.company_id.currency_id.id,
                "date": payslip.date_to or fields.Date.context_today(payslip),
                "journal_id": payslip.payment_journal_id.id,
                "payment_method_line_id": payment_method.id,
                "memo": _("Paiement du salaire — %s") % (payslip.number or payslip.name),
                "payroll_payslip_id": payslip.id,
                "payroll_salary_account_id": payslip.salary_account_id.id,
            })
            payment.action_post()
            payslip.write({
                "paid": True,
                "payment_id": payment.id,
                "payment_move_id": payment.move_id.id,
            })
        return True

    def action_open_payment_move(self):
        """Open the accounting entry created by the payslip payment."""
        self.ensure_one()
        if self.payment_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Paiement du salaire"),
                "res_model": "account.payment",
                "res_id": self.payment_id.id,
                "view_mode": "form",
                "target": "current",
            }
        if not self.payment_move_id:
            raise UserError(_("Aucun paiement comptable n'a encore été enregistré."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Paiement du salaire"),
            "res_model": "account.move",
            "res_id": self.payment_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_refund_payslip(self):
        """Open the return payslip linked to this original payslip."""
        self.ensure_one()
        if not self.refunded_id:
            raise UserError(_("Aucun avoir n'a été créé pour ce bulletin."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Avoir de paie"),
            "res_model": "hr.payslip",
            "res_id": self.refunded_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_payslip_cancel(self):
        for payslip in self:
            if payslip.paid and not payslip.refunded_id:
                raise UserError(_(
                    "Un bulletin payé doit d'abord faire l'objet d'un avoir."
                ))
            if payslip.allow_cancel_payslips:
                if payslip.refunded_id and payslip.refunded_id.state != "cancel":
                    raise ValidationError(
                        _(
                            """To cancel the Original Payslip the
                        Refunded Payslip needs to be canceled first!"""
                        )
                    )
            else:
                if self.filtered(lambda slip: slip.state == "done"):
                    raise UserError(_("Cannot cancel a payslip that is done."))
        return self.write({"state": "cancel"})

    def refund_sheet(self):
        copied_payslips = self.env["hr.payslip"]
        for payslip in self:
            if payslip.refunded_id and payslip.refunded_id.state != "cancel":
                raise UserError(_("Un avoir existe déjà pour ce bulletin."))
            # Create a refund slip
            copied_payslip = payslip.copy(
                {
                    "credit_note": True,
                    "refund_origin_id": payslip.id,
                    "name": _("Avoir de %s") % (payslip.number or payslip.name),
                }
            )
            # Assign a number
            number = copied_payslip.number or self.env["ir.sequence"].next_by_code(
                "salary.slip"
            )
            copied_payslip.write({"number": number})
            # Validated refund slip
            copied_payslip.with_context(
                without_compute_sheet=True
            ).action_payslip_done()

            # A paid payslip must be reversed in accounting as part of its credit note.
            refund_values = {"refunded_id": copied_payslip.id}
            if payslip.payment_id:
                payment_method = payslip.payment_journal_id.inbound_payment_method_line_ids[:1]
                if not payment_method:
                    raise UserError(_(
                        "Configurez une méthode de paiement entrante sur le journal des salaires."
                    ))
                reversal = self.env["account.payment"].create({
                    "payment_type": "inbound",
                    "partner_type": "supplier",
                    "partner_id": payslip.payment_id.partner_id.id,
                    "amount": payslip.payment_id.amount,
                    "currency_id": payslip.payment_id.currency_id.id,
                    "date": fields.Date.context_today(payslip),
                    "journal_id": payslip.payment_journal_id.id,
                    "payment_method_line_id": payment_method.id,
                    "memo": _("Avoir de paiement salaire — %s") % (
                        payslip.number or payslip.name
                    ),
                    "payroll_payslip_id": copied_payslip.id,
                    "payroll_salary_account_id": payslip.salary_account_id.id,
                })
                reversal.action_post()
                copied_payslip.write({
                    "paid": True,
                    "payment_id": reversal.id,
                    "payment_move_id": reversal.move_id.id,
                })
                # The original payment is now fully counter-posted.
                refund_values["paid"] = False
            elif payslip.payment_move_id and payslip.payment_move_id.state == "posted":
                # Compatibility with payroll payments created before native
                # account.payment support was enabled.
                reversal = payslip.payment_move_id._reverse_moves([{
                    "date": fields.Date.context_today(payslip),
                    "ref": _("Avoir sur paiement de salaire — %s") % (
                        payslip.number or payslip.name
                    ),
                }])
                reversal.action_post()
                copied_payslip.write({
                    "paid": True,
                    "payment_move_id": reversal.id,
                })
                refund_values["paid"] = False
            # Write refund reference on payslip
            payslip.write(refund_values)
            # Add to list of refund slips
            copied_payslips |= copied_payslip
        # Action to open list view of refund slips
        formview_ref = self.env.ref("payroll.hr_payslip_view_form", False)
        treeview_ref = self.env.ref("payroll.hr_payslip_view_tree", False)
        res = {
            "name": _("Refund Payslip"),
            "view_mode": "list, form",
            "view_id": False,
            "res_model": "hr.payslip",
            "type": "ir.actions.act_window",
            "target": "current",
            "domain": [("id", "in", copied_payslips.ids)],
            "views": [
                (treeview_ref and treeview_ref.id or False, "list"),
                (formview_ref and formview_ref.id or False, "form"),
            ],
            "context": {},
        }
        return res

    def unlink(self):
        if any(self.filtered(lambda payslip: payslip.state not in ("draft", "cancel"))):
            raise UserError(
                _("You cannot delete a payslip which is not draft or cancelled")
            )
        return super().unlink()

    def compute_sheet(self):
        for payslip in self:
            payslip._check_payroll_period_availability()
            # delete old payslip lines
            payslip.line_ids.unlink()
            # write payslip lines
            number = payslip.number or self.env["ir.sequence"].next_by_code(
                "salary.slip"
            )
            lines = [(0, 0, line) for line in list(payslip.get_lines_dict().values())]
            payslip.write(
                {
                    "line_ids": lines,
                    "number": number,
                    "state": "verify",
                    "compute_date": fields.Date.today(),
                }
            )
            # The dashboard is stored so it must be refreshed explicitly
            # after the old lines have been replaced by the computed ones.
            payslip._compute_salary_kpi_html()
        return True

    def _check_payroll_period_availability(self):
        """Prevent calculating overlapping payslips for the same employee."""
        self.ensure_one()
        if not (self.employee_id and self.date_from and self.date_to):
            raise ValidationError(_("Renseignez l'employé et la période du bulletin."))
        if self.date_from > self.date_to:
            raise ValidationError(_("La date de début doit être antérieure à la date de fin."))
        duplicate = self.search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("state", "in", ("verify", "done")),
            ("date_from", "<=", self.date_to),
            ("date_to", ">=", self.date_from),
        ], limit=1)
        if duplicate:
            raise ValidationError(_(
                "Un bulletin existe déjà pour %(employee)s sur une période qui "
                "chevauche celle sélectionnée : du %(date_from)s au %(date_to)s."
            ) % {
                "employee": self.employee_id.name,
                "date_from": fields.Date.to_string(duplicate.date_from),
                "date_to": fields.Date.to_string(duplicate.date_to),
            })

    def _set_next_payslip_period(self):
        """Start after the last calculated/validated payslip for the employee."""
        for payslip in self:
            if not payslip.employee_id:
                continue
            previous = self.search([
                ("id", "!=", payslip.id),
                ("employee_id", "=", payslip.employee_id.id),
                ("state", "in", ("verify", "done")),
                ("date_to", "!=", False),
            ], order="date_to desc, id desc", limit=1)
            if previous:
                next_start = previous.date_to + timedelta(days=1)
                today = fields.Date.context_today(payslip)
                if next_start <= today:
                    payslip.date_from = next_start
                    payslip.date_to = today

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """
        @param contracts: Browse record of contracts
        @return: returns a list of dict containing the input that should be
        applied for the given contract between date_from and date_to
        """
        res = []
        for contract in contracts.filtered(
            lambda contract: contract.resource_calendar_id
        ):
            day_from = datetime.combine(date_from, time.min)
            day_to = datetime.combine(date_to, time.max)
            day_contract_start = datetime.combine(contract.date_start, time.min)
            # Support for the hr_public_holidays module.
            contract = contract.with_context(
                employee_id=self.employee_id.id, exclude_public_holidays=True
            )
            # only use payslip day_from if it's greather than contract start date
            if day_from < day_contract_start:
                day_from = day_contract_start
            # == compute leave days == #
            leaves = self._compute_leave_days(contract, day_from, day_to)
            res.extend(leaves)
            # == compute worked days == #
            attendances = self._compute_worked_days(contract, day_from, day_to)
            res.append(attendances)
        return res

    def _compute_leave_days(self, contract, day_from, day_to):
        """
        Leave days computation
        @return: returns a list containing the leave inputs for the period
        of the payslip. One record per leave type.
        """
        leaves_positive = (
            self.env["ir.config_parameter"].sudo().get_param("payroll.leaves_positive")
        )
        leaves = {}
        calendar = contract.resource_calendar_id
        tz = timezone(calendar.tz)
        day_leave_intervals = contract.employee_id.list_leaves(
            day_from, day_to, calendar=contract.resource_calendar_id
        )
        for day, hours, leave in day_leave_intervals:
            holiday = leave[:1].holiday_id
            current_leave_struct = leaves.setdefault(
                holiday.holiday_status_id,
                {
                    "name": holiday.holiday_status_id.name or _("Global Leaves"),
                    "sequence": getattr(
                        getattr(holiday.holiday_status_id, "work_entry_type_id", None),
                        "sequence",
                        5,
                    ),
                    "code": getattr(
                        getattr(holiday.holiday_status_id, "work_entry_type_id", None),
                        "code",
                        "GLOBAL",
                    ),
                    "number_of_days": 0.0,
                    "number_of_hours": 0.0,
                    "contract_id": contract.id,
                },
            )
            if leaves_positive:
                current_leave_struct["number_of_hours"] += hours
            else:
                current_leave_struct["number_of_hours"] -= hours
            work_hours = calendar.get_work_hours_count(
                tz.localize(datetime.combine(day, time.min)),
                tz.localize(datetime.combine(day, time.max)),
                compute_leaves=False,
            )
            if work_hours:
                if leaves_positive:
                    current_leave_struct["number_of_days"] += hours / work_hours
                else:
                    current_leave_struct["number_of_days"] -= hours / work_hours
        return leaves.values()

    def _compute_worked_days(self, contract, day_from, day_to):
        """
        Worked days computation
        @return: returns a list containing the total worked_days for the period
        of the payslip. This returns the FULL work days expected for the resource
        calendar selected for the employee (it don't substract leaves by default).
        """
        work_data = contract.employee_id._get_work_days_data_batch(
            day_from,
            day_to,
            calendar=contract.resource_calendar_id,
            compute_leaves=False,
        )
        # Sans pointage, la base de paie est toujours de 30 jours par cycle.
        # Les mois de 28, 29 ou 31 jours ne modifient donc jamais le salaire
        # mensuel convenu. Les heures, elles, restent déterminées par l'horaire
        # du contrat.
        payable_days = self._get_payable_days(
            contract, day_from.date(), day_to.date()
        )
        return {
            "name": _("Normal Working Days paid at 100%"),
            "sequence": 1,
            "code": "WORK100",
            "number_of_days": payable_days,
            "number_of_hours": work_data[contract.employee_id.id]["hours"],
            "contract_id": contract.id,
        }

    def _get_payable_days(self, contract, date_from=None, date_to=None):
        """Return paid days using a fixed 30-day base for every pay cycle."""
        self.ensure_one()
        date_from = date_from or self.date_from
        date_to = date_to or self.date_to
        if not (date_from and date_to and contract):
            return 0.0
        period_start = max(date_from, contract.date_start)
        period_end = date_to
        if contract.date_end:
            period_end = min(period_end, contract.date_end)
        if period_start > period_end:
            return 0.0

        payable_days = 0.0
        cursor = period_start
        while cursor <= period_end:
            cycle_start, cycle_end = self._get_payment_cycle_bounds(contract, cursor)
            selected_end = min(period_end, cycle_end)
            selected_days = (selected_end - cursor).days + 1
            # A complete salary cycle always represents thirty paid days,
            # regardless of the calendar month length (including February).
            cycle_is_truncated_by_contract_end = (
                contract.date_end and cycle_end == contract.date_end
            )
            if (
                cursor == cycle_start
                and selected_end == cycle_end
                and not cycle_is_truncated_by_contract_end
            ):
                payable_days += 30.0
            else:
                payable_days += min(selected_days, 30)
            cursor = selected_end + timedelta(days=1)
        return payable_days

    def _get_work_time_proration(self, contract):
        """Compute the salary ratio from the fixed 30-day payroll basis."""
        return self._get_payable_days(contract) / 30.0

    def _get_payment_cycle_bounds(self, contract, target_date):
        """Return the salary cycle containing ``target_date``.

        Monthly cycles deliberately start on the contract anniversary date.  A
        contract that starts on 12 June therefore has a cycle from 12 June to
        11 July; an advance and its complement are calculated from that same
        reference period.
        """
        start = contract.date_start
        frequency = contract.schedule_pay or "monthly"
        if frequency == "weekly":
            step = relativedelta(weeks=1)
        elif frequency == "bi-weekly":
            step = relativedelta(weeks=2)
        elif frequency == "bi-monthly":
            step = relativedelta(months=2)
        elif frequency == "quarterly":
            step = relativedelta(months=3)
        elif frequency == "semi-annually":
            step = relativedelta(months=6)
        elif frequency == "annually":
            step = relativedelta(years=1)
        else:
            step = relativedelta(months=1)

        # Monthly contracts are anchored on the day configured on the contract,
        # rather than on the contract's creation/start anniversary.
        if frequency == "monthly":
            cycle_start = self._get_contract_payment_anchor(contract, target_date.year, target_date.month)
            if cycle_start > target_date:
                previous = target_date - relativedelta(months=1)
                cycle_start = self._get_contract_payment_anchor(contract, previous.year, previous.month)
        else:
            cycle_start = start
            while cycle_start + step <= target_date:
                cycle_start += step
        cycle_end = cycle_start + step - timedelta(days=1)
        if contract.date_end:
            cycle_end = min(cycle_end, contract.date_end)
        return cycle_start, cycle_end

    @api.model
    def _get_contract_payment_anchor(self, contract, year, month):
        """Return the contract payday, clamped for February and short months."""
        payment_day = max(1, min(contract.payroll_payment_day or 1, 31))
        return date(year, month, min(payment_day, monthrange(year, month)[1]))

    @api.onchange("contract_id")
    def _onchange_contract_payment_period(self):
        for payslip in self:
            if not (payslip.contract_id and payslip.date_to):
                continue
            start, _end = payslip._get_payment_cycle_bounds(
                payslip.contract_id, payslip.date_to
            )
            payslip.date_from = max(start, payslip.contract_id.date_start)

    @api.depends("employee_id", "contract_id", "date_from", "date_to")
    def _compute_period_worked_time(self):
        for payslip in self:
            payslip.period_worked_days = 0.0
            payslip.period_worked_hours = 0.0
            contract = payslip.contract_id or payslip._get_employee_contracts()[:1]
            if not (contract and payslip.date_from and payslip.date_to):
                continue
            start = max(payslip.date_from, contract.date_start)
            end = min(payslip.date_to, contract.date_end or payslip.date_to)
            if start > end or not contract.resource_calendar_id:
                continue
            data = contract.employee_id._get_work_days_data_batch(
                datetime.combine(start, time.min),
                datetime.combine(end, time.max),
                calendar=contract.resource_calendar_id,
                compute_leaves=False,
            )[contract.employee_id.id]
            payslip.period_worked_days = payslip._get_payable_days(contract, start, end)
            payslip.period_worked_hours = data["hours"]

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        # TODO: We leave date_from and date_to params here for backwards
        # compatibility reasons for the ones who inherit this function
        # in another modules, but they are not used.
        # Will be removed in next versions.
        """
        Inputs computation.
        @returns: Returns a dict with the inputs that are fetched from the salary_structure
        associated rules for the given contracts.
        """  # noqa: E501
        res = []
        payslip_inputs = self._get_salary_rules().input_ids
        for contract in contracts:
            for payslip_input in payslip_inputs:
                res.append(
                    {
                        "name": payslip_input.name,
                        "code": payslip_input.code,
                        "contract_id": contract.id,
                    }
                )
        return res

    def _init_payroll_dict_contracts(self):
        return {
            "count": 0,
        }

    def get_payroll_dict(self, contracts):
        """Setup miscellaneous dictionary values.
        Other modules may overload this method to inject discreet values into
        the salary rules. Such values will be available to the salary rule
        under the `payroll.` prefix.

        This method is evaluated once per payslip.
        :param contracts: Recordset of all hr.contract records in this payslip
        :return: a dictionary of discreet values and/or Browsable Objects
        """
        self.ensure_one()

        res = {
            # In salary rules refer to this as: payroll.contracts.count
            "contracts": BaseBrowsableObject(self._init_payroll_dict_contracts()),
        }
        res["contracts"].count = len(contracts)

        return res

    def get_current_contract_dict(self, contract, contracts):
        """Contract dependent dictionary values.
        This method is called just before the salary rules are evaluated for
        contract.

        This method is evaluated once for every contract in the payslip.

        :param contract: The current hr.contract being processed
        :param contracts: Recordset of all hr.contract records in this payslip
        :return: a dictionary of discreet values and/or Browsable Objects
        """
        self.ensure_one()

        # res = super().get_current_contract_dict(contract, contracts)
        # res.update({
        #     # In salary rules refer to these as:
        #     #     current_contract.foo
        #     #     current_contract.foo.bar.baz
        #     "foo": 0,
        #     "bar": BaseBrowsableObject(
        #         {
        #             "baz": 0
        #         }
        #     )
        # })
        # <do something to update values in res>
        # return res

        ratio = self._get_work_time_proration(contract)
        prorated_wage = math.ceil(contract.wage * ratio)
        return {
            # Available in Python salary rules as
            # ``current_contract.worked_time_ratio``.
            "worked_time_ratio": ratio,
            # Salary from the employee contract, prorated to the selected
            # period and rounded up before it is used by salary rules.
            "base_salary": prorated_wage,
            "prorated_wage": prorated_wage,
        }

    def _get_tools_dict(self):
        # _get_tools_dict() is intended to be inherited by other private modules
        # to add tools or python libraries available in localdict
        return {"math": math}  # "math" object is useful for doing calculations

    def _get_baselocaldict(self, contracts):
        self.ensure_one()
        worked_days_dict = {
            line.code: line for line in self.worked_days_line_ids if line.code
        }
        input_lines_dict = {
            line.code: line for line in self.input_line_ids if line.code
        }
        localdict = {
            "payslips": Payslips(self.employee_id.id, self, self.env),
            "worked_days": WorkedDays(self.employee_id.id, worked_days_dict, self.env),
            "inputs": InputLine(self.employee_id.id, input_lines_dict, self.env),
            "payroll": BrowsableObject(
                self.employee_id.id, self.get_payroll_dict(contracts), self.env
            ),
            "current_contract": BrowsableObject(self.employee_id.id, {}, self.env),
            "categories": BrowsableObject(self.employee_id.id, {}, self.env),
            "rules": BrowsableObject(self.employee_id.id, {}, self.env),
            "result_rules": BrowsableObject(self.employee_id.id, {}, self.env),
            "tools": BrowsableObject(
                self.employee_id.id, self._get_tools_dict(), self.env
            ),
        }
        return localdict

    def _get_salary_rules(self):
        "Return rules for the Paylips, sorted by sequence"
        current_structures = self._get_selected_salary_structures() if self else False
        if current_structures:
            structures = self.env["hr.payroll.structure"]
            for structure in current_structures:
                structures |= structure.get_structure_with_parents()
        else:
            contracts = self._get_employee_contracts()
            structures = contracts.struct_id.get_structure_with_parents()
        return structures.get_all_rules()

    def _get_selected_salary_structures(self):
        """Structures directement choisies, sans dupliquer la principale."""
        self.ensure_one()
        return self.struct_id | self.struct_ids

    def _get_salary_structures_with_parents(self):
        """Structures effectives avec leurs parents, sans doublons."""
        self.ensure_one()
        structures = self.env["hr.payroll.structure"]
        for structure in self._get_selected_salary_structures():
            structures |= structure.get_structure_with_parents()
        return structures

    def _compute_payslip_line(self, rule, localdict, lines_dict):
        self.ensure_one()
        # check if there is already a rule computed with that code
        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
        # compute the rule to get some values for the payslip line
        values = rule._compute_rule(localdict)
        uses_prorated_wage = rule._uses_prorated_wage()
        if rule._is_direct_period_proration_rule() and not uses_prorated_wage:
            prorated_amount = (
                values["amount"] * localdict["current_contract"].worked_time_ratio
            )
            # The negotiated salary and every fixed salary rule are prorated
            # on 30 days, then rounded away from zero.  Example: 100,000 / 30
            # * 5 becomes 16,667 FCFA.
            values["amount"] = (
                math.ceil(prorated_amount)
                if prorated_amount >= 0
                else -math.ceil(abs(prorated_amount))
            )
        key = (rule.code or "id" + str(rule.id)) + "-" + str(localdict["contract"].id)
        return self._get_lines_dict(
            rule, localdict, lines_dict, key, values, previous_amount
        )

    def _get_lines_dict(
        self, rule, localdict, lines_dict, key, values, previous_amount
    ):
        total = values["quantity"] * values["rate"] * values["amount"] / 100.0
        values["total"] = total
        # set/overwrite the amount computed for this rule in the localdict
        if rule.code:
            localdict[rule.code] = total
            localdict["rules"].dict[rule.code] = rule
            localdict["result_rules"].dict[rule.code] = BaseBrowsableObject(values)
        # sum the amount for its salary category
        localdict = self._sum_salary_rule_category(
            localdict, rule.category_id, total - previous_amount
        )
        # create/overwrite the line in the temporary results
        line_dict = {
            "salary_rule_id": rule.id,
            "employee_id": localdict["employee"].id,
            "contract_id": localdict["contract"].id,
            "code": rule.code,
            "category_id": rule.category_id.id,
            "sequence": rule.sequence,
            "appears_on_payslip": rule.appears_on_payslip,
            "parent_rule_id": rule.parent_rule_id.id,
            "condition_select": rule.condition_select,
            "condition_python": rule.condition_python,
            "condition_range": rule.condition_range,
            "condition_range_min": rule.condition_range_min,
            "condition_range_max": rule.condition_range_max,
            "amount_select": rule.amount_select,
            "amount_fix": rule.amount_fix,
            "amount_python_compute": rule.amount_python_compute,
            "amount_percentage": rule.amount_percentage,
            "amount_percentage_base": rule.amount_percentage_base,
            "register_id": rule.register_id.id,
            "proration_percentage": (
                localdict["current_contract"].worked_time_ratio * 100
            ),
            "proration_base_amount": localdict["current_contract"].prorated_wage,
        }
        line_dict.update(values)
        lines_dict[key] = line_dict
        return localdict, lines_dict

    @api.model
    def _get_payslip_lines(self, _contract_ids, payslip_id):
        _logger.warning(
            "Use of _get_payslip_lines() is deprecated. "
            "Use get_lines_dict() instead."
        )
        return self.browse(payslip_id).get_lines_dict()

    def get_lines_dict(self):
        lines_dict = {}
        blacklist = self.env["hr.salary.rule"]
        for payslip in self:
            contracts = payslip._get_employee_contracts()
            baselocaldict = payslip._get_baselocaldict(contracts)
            for contract in contracts:
                # assign "current_contract" dict
                baselocaldict["current_contract"] = BrowsableObject(
                    payslip.employee_id.id,
                    payslip.get_current_contract_dict(contract, contracts),
                    payslip.env,
                )
                # set up localdict with current contract and employee values
                localdict = dict(
                    baselocaldict,
                    employee=contract.employee_id,
                    # Existing rules using ``contract.wage`` receive the
                    # exact prorated negotiated salary for this bulletin.
                    contract=ProratedContract(
                        contract,
                        baselocaldict["current_contract"].prorated_wage,
                    ),
                    payslip=payslip,
                )
                for rule in payslip._get_salary_rules():
                    localdict = rule._reset_localdict_values(localdict)
                    # check if the rule can be applied
                    if rule._satisfy_condition(localdict) and rule not in blacklist:
                        localdict, _dict = payslip._compute_payslip_line(
                            rule, localdict, lines_dict
                        )
                        lines_dict.update(_dict)
                    else:
                        # blacklist this rule and its children
                        blacklist += rule._recursive_search_of_rules()
                # call localdict_hook
                localdict = payslip.localdict_hook(localdict)
                # reset "current_contract" dict
                baselocaldict["current_contract"] = {}
        return lines_dict

    def localdict_hook(self, localdict):
        # This hook is called when the function _get_lines_dict ends the loop
        # and before its returns. This method by itself don't add any functionality
        # and is intedend to be inherited to access localdict from other functions.
        return localdict

    def get_payslip_vals(
        self, date_from, date_to, employee_id=False, contract_id=False, struct_id=False
    ):
        # Initial default values for generated payslips
        employee = self.env["hr.employee"].browse(employee_id)
        res = {
            "value": {
                "line_ids": [],
                "input_line_ids": [(2, x) for x in self.input_line_ids.ids],
                "worked_days_line_ids": [(2, x) for x in self.worked_days_line_ids.ids],
                "name": "",
                "contract_id": False,
                "struct_id": False,
                "struct_ids": [(5, 0, 0)],
            }
        }
        # If we don't have employee or date data, we return.
        if (not employee_id) or (not date_from) or (not date_to):
            return res
        # We check if contract_id is present, if not we fill with the
        # first contract of the employee. If not contract present, we return.
        if not self.env.context.get("contract"):
            contract_ids = employee.contract_id.ids
        else:
            if contract_id:
                contract_ids = [contract_id]
            else:
                contract_ids = employee._get_contracts(
                    date_from=date_from, date_to=date_to
                ).ids
        if not contract_ids:
            return res
        contract = self.env["hr.contract"].browse(contract_ids[0])
        res["value"].update({"contract_id": contract.id})
        # We check if struct_id is already filled, otherwise we assign the contract struct. # noqa: E501
        # If contract don't have a struct, we return.
        contract_structures = contract.struct_ids or contract.struct_id
        if struct_id:
            selected_struct_id = struct_id[0]
            res["value"].update(
                {
                    "struct_id": selected_struct_id,
                    "struct_ids": [(6, 0, [selected_struct_id])],
                }
            )
        else:
            if not contract_structures:
                return res
            res["value"].update(
                {
                    "struct_id": contract_structures[0].id,
                    "struct_ids": [(6, 0, contract_structures.ids)],
                }
            )
        # Computation of the salary input and worked_day_lines
        contracts = self.env["hr.contract"].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        res["value"].update(
            {
                "worked_days_line_ids": worked_days_line_ids,
                "input_line_ids": input_line_ids,
            }
        )
        return res

    def _sum_salary_rule_category(self, localdict, category, amount):
        self.ensure_one()
        if category.parent_id:
            localdict = self._sum_salary_rule_category(
                localdict, category.parent_id, amount
            )
        if category.code:
            localdict["categories"].dict[category.code] = (
                localdict["categories"].dict.get(category.code, 0) + amount
            )
        return localdict

    def _get_employee_contracts(self):
        contracts = self.env["hr.contract"]
        for payslip in self:
            if payslip.contract_id.ids:
                contracts |= payslip.contract_id
            else:
                contracts |= payslip.employee_id._get_contracts(
                    date_from=payslip.date_from, date_to=payslip.date_to
                )
        return contracts

    @api.onchange("struct_id")
    def onchange_struct_id(self):
        for payslip in self:
            if payslip.struct_id and payslip.struct_id not in payslip.struct_ids:
                payslip.struct_ids |= payslip.struct_id
            if not payslip.struct_id:
                if not payslip.struct_ids:
                    payslip.input_line_ids.unlink()
                    return
            input_lines = payslip.input_line_ids.browse([])
            input_line_ids = payslip.get_inputs(
                payslip._get_employee_contracts(), payslip.date_from, payslip.date_to
            )
            for r in input_line_ids:
                input_lines += input_lines.new(r)
            payslip.input_line_ids = input_lines

    @api.onchange("struct_ids")
    def onchange_struct_ids(self):
        for payslip in self:
            if not payslip.struct_ids:
                payslip.struct_id = False
            elif payslip.struct_id not in payslip.struct_ids:
                payslip.struct_id = payslip.struct_ids[0]
            payslip.onchange_struct_id()

    @api.onchange("date_from", "date_to")
    def onchange_dates(self):
        for payslip in self:
            if not payslip.date_from or not payslip.date_to:
                return
            worked_days_lines = payslip.worked_days_line_ids.browse([])
            worked_days_line_ids = payslip.get_worked_day_lines(
                payslip._get_employee_contracts(), payslip.date_from, payslip.date_to
            )
            for line in worked_days_line_ids:
                worked_days_lines += worked_days_lines.new(line)
            payslip.worked_days_line_ids = worked_days_lines
            payslip._compute_name()

    @api.onchange("employee_id")
    def onchange_employee(self):
        for payslip in self:
            # Return if required values are not present.
            if (
                (not payslip.employee_id)
                or (not payslip.date_from)
                or (not payslip.date_to)
            ):
                continue
            # Assign contract_id automatically when the user don't selected one.
            if not payslip.env.context.get("contract") or not payslip.contract_id:
                contract_ids = payslip._get_employee_contracts().ids
                if not contract_ids:
                    continue
                payslip.contract_id = payslip.env["hr.contract"].browse(contract_ids[0])
                # L'employé vient d'être choisi : ouvrir immédiatement le
                # cycle correspondant au jour de paie de son contrat.
                payslip._onchange_contract_payment_period()
                payslip._set_next_payslip_period()
            # Assign struct_id automatically when the user don't selected one.
            if not payslip.struct_id and not payslip.env.context.get("struct_id"):
                contract_structures = payslip.contract_id.struct_ids or payslip.contract_id.struct_id
                if not contract_structures:
                    continue
                payslip.struct_id = contract_structures[0]
                payslip.struct_ids = [(6, 0, contract_structures.ids)]
            # Compute payslip name
            payslip._compute_name()
            # Call worked_days_lines computation when employee is changed.
            payslip.onchange_dates()
            # Call input_lines computation when employee is changed.
            payslip.onchange_struct_id()
            # Assign company_id automatically based on employee selected.
            payslip.company_id = payslip.employee_id.company_id
            if (
                not payslip.payment_journal_id
                or payslip.payment_journal_id.company_id != payslip.company_id
            ):
                payslip.payment_journal_id = payslip._get_default_payment_journal(
                    payslip.company_id
                )
            if (
                not payslip.salary_account_id
                or payslip.company_id not in payslip.salary_account_id.company_ids
            ):
                payslip.salary_account_id = payslip._get_default_salary_account(
                    payslip.company_id
                )

    def _compute_name(self):
        for record in self:
            if not (record.employee_id and record.date_from and record.date_to):
                continue
            locale = record.env.context.get("lang") or "en_US"
            date_from = babel.dates.format_date(
                date=record.date_from, format="short", locale=locale
            )
            date_to = babel.dates.format_date(
                date=record.date_to, format="short", locale=locale
            )
            record.name = _("Bulletin de paie de %(name)s — du %(date_from)s au %(date_to)s") % {
                "name": record.employee_id.name,
                "date_from": str(date_from),
                "date_to": str(date_to),
            }

    @api.onchange("contract_id")
    def onchange_contract(self):
        if not self.contract_id:
            self.struct_id = False
            self.struct_ids = [(5, 0, 0)]
        else:
            contract_structures = self.contract_id.struct_ids or self.contract_id.struct_id
            if contract_structures:
                self.struct_id = contract_structures[0]
                self.struct_ids = [(6, 0, contract_structures.ids)]
        self._onchange_contract_payment_period()
        self._set_next_payslip_period()
        self.with_context(contract=True).onchange_employee()
        return

    def get_salary_line_total(self, code):
        self.ensure_one()
        line = self.line_ids.filtered(lambda line: line.code == code)
        if line:
            return line[0].total
        else:
            return 0.0

    def _get_report_line_structure(self, line):
        """Trouve la structure la plus proche du bulletin contenant la règle."""
        self.ensure_one()
        structures = self._get_salary_structures_with_parents()
        rules = line.salary_rule_id
        parent_rule = line.salary_rule_id.parent_rule_id
        while parent_rule and parent_rule not in rules:
            rules |= parent_rule
            parent_rule = parent_rule.parent_rule_id
        for structure in reversed(structures):
            if structure.rule_ids & rules:
                return structure
        return self.struct_id or self.struct_ids[:1]

    def _get_report_line_kind(self, line, structure=False):
        """Classe une ligne dans les colonnes salariales ou patronales."""
        code = (line.code or "").upper()
        if code in {"GROSS", "BRUT", "SAL_BRUT"}:
            return "summary"
        if line.report_section == "information":
            return "information"
        report_side = structure.report_side if structure else "mixed"
        if report_side == "employer":
            return "employer"
        if report_side == "employee":
            return "deduction" if line.total < 0 else "gain"
        if line.report_section == "employer":
            return "employer"
        if line.report_section == "deduction" or (
            line.report_section == "auto" and line.total < 0
        ):
            return "deduction"
        return "gain"

    def _get_report_structure_groups(self):
        """Prépare les lignes et sous-totaux du bulletin, groupés par structure."""
        self.ensure_one()
        net_codes = {"NET", "SN", "SAL_NET"}
        groups = {}
        for line in self.line_ids.filtered("appears_on_payslip").sorted("sequence"):
            if (line.code or "").upper() in net_codes:
                continue
            structure = self._get_report_line_structure(line)
            key = structure.id if structure else 0
            if key not in groups:
                report_side = structure.report_side if structure else "mixed"
                groups[key] = {
                    "structure_id": key,
                    "name": structure.name if structure else _("Éléments non rattachés"),
                    "report_side": report_side,
                    "side_label": dict(
                        self.env["hr.payroll.structure"]._fields[
                            "report_side"
                        ]._description_selection(self.env)
                    ).get(report_side, ""),
                    "items": [],
                    "gain_total": 0.0,
                    "deduction_total": 0.0,
                    "employer_total": 0.0,
                }
            kind = self._get_report_line_kind(line, structure)
            groups[key]["items"].append({"line": line, "kind": kind})
            if kind == "gain":
                groups[key]["gain_total"] += abs(line.total)
            elif kind == "deduction":
                groups[key]["deduction_total"] += abs(line.total)
            elif kind == "employer":
                groups[key]["employer_total"] += abs(line.total)
        for group in groups.values():
            group["subtotal"] = (
                group["employer_total"]
                if group["report_side"] == "employer"
                else group["gain_total"] - group["deduction_total"]
            )
        return list(groups.values())

    def _dashboard_amounts(self):
        """Retourne les montants du bulletin selon la formule de paie retenue."""
        self.ensure_one()
        gross_codes = {"GROSS", "BRUT", "SAL_BRUT"}
        lines = self.line_ids.filtered("appears_on_payslip")
        explicit_gross = sum(
            abs(line.total)
            for line in lines
            if (line.code or "").upper() in gross_codes
        )
        groups = self._get_report_structure_groups()
        fallback_gross = sum(group["gain_total"] for group in groups)
        deductions = sum(group["deduction_total"] for group in groups)
        employer = sum(group["employer_total"] for group in groups)
        gross = explicit_gross or fallback_gross
        # Règle métier : net à payer = salaire brut - retenues salariales
        # - charges patronales. La ligne technique NET éventuelle ne remplace
        # pas ce calcul afin de garder le rapport et le tableau de bord cohérents.
        net = gross - deductions - employer
        return {
            "gross": gross,
            "net": net,
            "deductions": deductions,
            "employer": employer,
        }

    @api.model
    def _dashboard_buckets(self, date_from, date_to):
        """Regroupe la paie au mois, au trimestre ou au semestre uniquement."""
        days = (date_to - date_from).days + 1
        buckets = []
        month_names = (
            "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
            "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
        )
        current = date_from.replace(day=1)
        if days <= 550:
            while current <= date_to:
                end = min(current + relativedelta(months=1, days=-1), date_to)
                start = max(current, date_from)
                buckets.append((start, end, "%s %s" % (month_names[current.month - 1], current.year)))
                current += relativedelta(months=1)
        elif days <= 1460:
            quarter_month = ((current.month - 1) // 3) * 3 + 1
            current = current.replace(month=quarter_month, day=1)
            while current <= date_to:
                end = min(current + relativedelta(months=3, days=-1), date_to)
                start = max(current, date_from)
                quarter = ((current.month - 1) // 3) + 1
                buckets.append((start, end, "T%s %s" % (quarter, current.year)))
                current += relativedelta(months=3)
        else:
            semester_month = 1 if current.month <= 6 else 7
            current = current.replace(month=semester_month, day=1)
            while current <= date_to:
                end = min(current + relativedelta(months=6, days=-1), date_to)
                semester = 1 if current.month == 1 else 2
                buckets.append((max(current, date_from), end, "S%s %s" % (semester, current.year)))
                current += relativedelta(months=6)
        return buckets

    @api.model
    def get_payroll_dashboard_data(self, date_from=None, date_to=None):
        """Données réelles, préchargées en une requête de bulletins par période."""
        today = fields.Date.context_today(self)
        start = fields.Date.to_date(date_from) if date_from else today.replace(day=1)
        end = fields.Date.to_date(date_to) if date_to else today
        if start > end:
            raise ValidationError(_("La date de début doit précéder la date de fin."))

        company_id = self.env.company.id
        domain = [
            ("company_id", "=", company_id),
            ("date_to", ">=", start),
            ("date_to", "<=", end),
        ]
        payslips = self.search(domain, order="date_to desc, id desc")
        done_slips = payslips.filtered(lambda slip: slip.state == "done" and not slip.credit_note)
        amount_by_id = {slip.id: slip._dashboard_amounts() for slip in done_slips}

        totals = {"gross": 0.0, "net": 0.0, "deductions": 0.0, "employer": 0.0}
        for amounts in amount_by_id.values():
            for key in totals:
                totals[key] += amounts[key]

        state_labels = {
            "draft": _("Brouillons"),
            "verify": _("En attente"),
            "done": _("Validés"),
            "cancel": _("Rejetés"),
        }
        state_colors = {
            "draft": "var(--o-gray-500, #7c8798)",
            "verify": "#f0ad4e",
            "done": "var(--o-success, #28a745)",
            "cancel": "var(--o-danger, #dc3545)",
        }
        state_count = defaultdict(int)
        for slip in payslips:
            state_count[slip.state] += 1
        total_count = len(payslips) or 1
        statuses = [
            {
                "key": key,
                "label": state_labels[key],
                "count": state_count[key],
                "percent": round(state_count[key] * 100 / total_count, 1),
                "color": state_colors[key],
            }
            for key in ("done", "verify", "draft", "cancel")
        ]

        evolution = []
        for bucket_start, bucket_end, label in self._dashboard_buckets(start, end):
            selected = done_slips.filtered(
                lambda slip, bs=bucket_start, be=bucket_end: bs <= slip.date_to <= be
            )
            evolution.append({
                "label": label,
                "date_from": fields.Date.to_string(bucket_start),
                "date_to": fields.Date.to_string(bucket_end),
                "gross": sum(amount_by_id[slip.id]["gross"] for slip in selected),
                "net": sum(amount_by_id[slip.id]["net"] for slip in selected),
                "count": len(selected),
            })
        evolution_max = max(
            [max(point["gross"], point["net"]) for point in evolution] or [1.0]
        ) or 1.0
        for point in evolution:
            point["gross_height"] = max(3, round(point["gross"] * 100 / evolution_max)) if point["gross"] else 0
            point["net_height"] = max(3, round(point["net"] * 100 / evolution_max)) if point["net"] else 0

        departments = defaultdict(lambda: {"total": 0.0, "count": 0, "employee_ids": set()})
        employees = defaultdict(lambda: {"net": 0.0, "gross": 0.0, "count": 0, "record": False})
        for slip in done_slips:
            amounts = amount_by_id[slip.id]
            employee = slip.employee_id
            department = employee.department_id
            dept_key = department.id or 0
            departments[dept_key]["name"] = department.name or _("Sans département")
            departments[dept_key]["total"] += amounts["net"]
            departments[dept_key]["count"] += 1
            departments[dept_key]["employee_ids"].add(employee.id)
            employees[employee.id]["record"] = employee
            employees[employee.id]["net"] += amounts["net"]
            employees[employee.id]["gross"] += amounts["gross"]
            employees[employee.id]["count"] += 1

        department_rows = sorted(departments.items(), key=lambda item: item[1]["total"], reverse=True)
        department_max = max([row[1]["total"] for row in department_rows] or [1.0]) or 1.0
        department_data = [
            {
                "id": dept_id,
                "name": values["name"],
                "total": values["total"],
                "count": values["count"],
                "employees": len(values["employee_ids"]),
                "percent": round(values["total"] * 100 / department_max),
            }
            for dept_id, values in department_rows[:8]
        ]

        employee_rows = sorted(employees.items(), key=lambda item: item[1]["net"], reverse=True)
        employee_max = max([row[1]["net"] for row in employee_rows] or [1.0]) or 1.0
        top_employees = []
        for employee_id, values in employee_rows[:8]:
            employee = values["record"]
            top_employees.append({
                "id": employee_id,
                "name": employee.name,
                "job": employee.job_id.name or _("Poste non renseigné"),
                "department": employee.department_id.name or _("Sans département"),
                "net": values["net"],
                "gross": values["gross"],
                "count": values["count"],
                "percent": round(values["net"] * 100 / employee_max),
            })

        state_selection = dict(self._fields["state"]._description_selection(self.env))
        recent = [
            {
                "id": slip.id,
                "name": slip.number or slip.name or _("Bulletin"),
                "employee": slip.employee_id.name,
                "date": fields.Date.to_string(slip.date_to),
                "state": slip.state,
                "state_label": state_selection.get(slip.state, slip.state),
                "net": amount_by_id.get(slip.id, {}).get("net", 0.0),
            }
            for slip in payslips[:8]
        ]

        currency = self.env.company.currency_id
        employees_count = len(set(done_slips.mapped("employee_id").ids))
        return {
            "company": self.env.company.name,
            "company_id": company_id,
            "date_from": fields.Date.to_string(start),
            "date_to": fields.Date.to_string(end),
            "currency": currency.name,
            "currency_symbol": currency.symbol,
            "kpis": {
                "payslips": len(payslips),
                "validated": len(done_slips),
                "employees": employees_count,
                "gross": totals["gross"],
                "net": totals["net"],
                "deductions": totals["deductions"],
                "employer": totals["employer"],
                "average_net": totals["net"] / employees_count if employees_count else 0.0,
            },
            "statuses": statuses,
            "evolution": evolution,
            "departments": department_data,
            "top_employees": top_employees,
            "recent": recent,
            "employee_ids": list(set(done_slips.mapped("employee_id").ids)),
        }
