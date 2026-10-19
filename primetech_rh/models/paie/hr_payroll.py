# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _
from datetime import date, datetime, timedelta
from odoo.exceptions import UserError, AccessError, ValidationError
import time
from dateutil import relativedelta


class ResCompany(models.Model):
    _inherit = 'res.company'

    cnps_num = fields.Char('CNPS Number')
    tax_num = fields.Char('Taxpayer number')


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _inherit = 'hr.payslip.run'

    period_id = fields.Many2one('hr.pai.period', string='Pay Period', compute="_get_pay_period", store=True)

    @api.depends('date_start')
    def _get_pay_period(self):
        if self.date_start:
            period = self.env['hr.pai.period'].search([('date_start', '<=', self.date_start), ('date_stop', '>=', self.date_start), ('state', '=', 'draft')])
            get = len(period) >= 1
            if get:
                self.period_id = period[0].id
            else:
                self.period_id = False
                raise ValidationError(_('Warning!\nNo pay period corresponds to this date.'))


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = 'hr.payslip'
    
    state = fields.Selection(selection_add=[
        ('paid', 'Paid')
    ], string='Status', index=True, readonly=True, copy=False, default='draft',
        help="""* When the payslip is created the status is \'Draft\'
                \n* If the payslip is under verification, the status is \'Waiting\'.
                \n* If the payslip is confirmed then status is set to \'Done\'.
                \n* When user cancel payslip the status is \'Rejected\'.""")
    seniority = fields.Integer('Seniority')
    period_id = fields.Many2one('hr.pai.period', string='Pay Period', compute="_get_pay_period", store=True)
    category_id = fields.Many2one('hr.employee.category', string='Category', tracking=True)
    echelon_id = fields.Many2one('hr.paie.echelon', string='Echelon', tracking=True)

    @api.depends('date_from')
    def _get_pay_period(self):
        if self.date_from:
            period = self.env['hr.pai.period'].search([('date_start', '<=', self.date_from), ('date_stop', '>=', self.date_from), ('state', '=', 'draft')])
            get = len(period) >= 1
            if get:
                self.period_id = period[0].id
            else:
                self.period_id = False
                self.date_from = False
                raise ValidationError(_('Warning!\nNo pay period corresponds to this date.'))

    def action_payslip_draft(self):
        return self.write({'state': 'draft'})

    def action_payslip_cancel(self):
        if self.filtered(lambda slip: slip.move_id.state == 'posted'):
            raise UserError(_("Cannot cancel a payslip that is done."))
        return self.write({'state': 'cancel'})
    
    def hr_pay_sheet(self):
        self.state = 'paid'

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """
        @param contract_ids: list of contract id
        @return: returns a list of dict containing the input that should be applied for the given contract between date_from and date_to
        """
        res = []
        for contract in contracts.filtered(lambda contract: contract.resource_calendar_id):
            work_days = 30
            work_hours = 173.33
            attendances = {
                 'name': _("Normal Working Days paid at 100%"),
                 'sequence': 1,
                 'code': 'WORK100',
                 'number_of_days': work_days,
                 'number_of_hours': work_hours,
                 'contract_id': contract.id,
            }
            res.append(attendances)
            res.append({
                'name': _("Days unpaid"),
                'sequence': 2,
                'code': 'UNPAID',
                'number_of_days': 0,
                'number_of_hours': 0,
                'contract_id': contract.id,
            })
        return res

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = []

        # ``get_all_structures`` returns an Odoo recordset.  The legacy
        # implementation passed that recordset back to ``browse()``, which
        # makes PostgreSQL try to adapt ``hr.payroll.structure`` as an SQL id.
        # Work directly with recordsets (Odoo 18 API).
        structures = contracts.get_all_structures()
        rule_ids = structures.get_all_rules()
        inputs = rule_ids.mapped("input_ids")

        for contract in contracts:
            contract_input_value = {}
            for value in contract.input_values_ids:
                contract_input_value[value.rule_input_id.id] = value.amount
            for input in inputs:
                if contract_input_value.get(input.id, 0) != 0:
                    input_data = {
                        'name': input.name,
                        'code': input.code,
                        'contract_id': contract.id,
                        'amount':contract_input_value.get(input.id, 0)
                    }
                    res += [input_data]
        return res

    def _get_seniority(self, employee, date_end):
        contract_obj = self.env['hr.contract']
        contract = contract_obj.search([('employee_id', '=', employee.id)], order='date_start asc', limit=1)

        def diff_month(d1, d2):
            return (d1.year - d2.year) * 12 + d1.month - d2.month

        if len(contract) > 0:
            date_start = contract.date_start
            diff = diff_month(date_end, date_start)
        else:
            diff = 0

        return diff

    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            if category.code in localdict['categories'].dict:
                amount += localdict['categories'].dict[category.code]
            localdict['categories'].dict[category.code] = amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                            (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

        #we keep a dict with the result because a value can be overwritten by another rule with the same code
        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []

        payslip = self.env['hr.payslip'].browse(payslip_id)
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict, self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        baselocaldict = {'categories': categories, 'rules': rules, 'payslip': payslips, 'worked_days': worked_days, 'inputs': inputs}
        #get the ids of the structures on the contracts and their parent id as well
        contracts = self.env['hr.contract'].browse(contract_ids)
        structures = contracts.get_all_structures()
        # Get and order the rules directly from the structure recordset.
        sorted_rules = structures.get_all_rules().sorted("sequence")

        for contract in contracts:
            employee = contract.employee_id
            localdict = dict(baselocaldict, employee=employee, contract=contract)
            for rule in sorted_rules:
                key = rule.code + '-' + str(contract.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                #check if the rule can be applied
                if rule._satisfy_condition(localdict) and rule.id not in blacklist:
                    #compute the amount of the rule
                    # if rule.amount_percentage_base and rule.amount_select == 'code':
                    #     print("####", rule.code, localdict[rule.amount_percentage_base])
                    amount, qty, rate = rule._compute_rule(localdict)
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = amount * qty * rate / 100.0
                    localdict[rule.code] = tot_rule
                    rules_dict[rule.code] = rule
                    #sum the amount for its salary category
                    localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                    #create/overwrite the rule in the temporary results
                    base = (rule.amount_percentage_base and rule.amount_select == 'code') and localdict[rule.amount_percentage_base] or amount
                    if amount > 0 and (rule.appears_on_payslip or rule.category_id.code == 'TOTAUX'):
                        result_dict[key] = {
                            'salary_rule_id': rule.id,
                            'contract_id': contract.id,
                            'name': rule.name,
                            'code': rule.code,
                            'category_id': rule.category_id.id,
                            'sequence': rule.sequence,
                            'appears_on_payslip': rule.appears_on_payslip,
                            'condition_select': rule.condition_select,
                            'condition_python': rule.condition_python,
                            'condition_range': rule.condition_range,
                            'condition_range_min': rule.condition_range_min,
                            'condition_range_max': rule.condition_range_max,
                            'amount_select': rule.amount_select,
                            'amount_fix': rule.amount_fix,
                            'amount_python_compute': rule.amount_python_compute,
                            'amount_percentage': rule.amount_percentage,
                            'amount_percentage_base': rule.amount_percentage_base,
                            'register_id': rule.register_id.id,
                            'base': base,
                            'amount': amount,
                            'employee_id': contract.employee_id.id,
                            'quantity': qty,
                            'rate': rate,
                        }
                else:
                    #blacklist this rule and its children
                    blacklist += [id for id, seq in rule._recursive_search_of_rules()]

        return [value for code, value in result_dict.items()]
    

    @api.onchange('employee_id', 'date_to')
    def onchange_contract_id(self):
        if self.employee_id and self.date_to:
            self.seniority = self._get_seniority(self.employee_id, self.date_to)


    @api.onchange('employee_id')
    def _onchange_employee(self):
        if self.employee_id:
            self.category_id = self.employee_id.category_id.id
            self.echelon_id = self.employee_id.echelon_id.id


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'
    
    base = fields.Float(digits=(16, 2), string='Base')
    appears_on_payslip = fields.Boolean(string='Appears on Payslip', related='salary_rule_id.appears_on_payslip', store='True')
    payslip_code = fields.Char('code', related='salary_rule_id.payslip_code', store='True')


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    compute_leave = fields.Boolean('Leave calculation', default=True)
    payslip_code = fields.Char('code')
    contrib = fields.Boolean('Contribution')
