# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _
from datetime import date, datetime, timedelta
from odoo.exceptions import UserError, AccessError, ValidationError
import time
from dateutil import relativedelta

class HrContractInputs(models.Model):
    _name = 'hr.contract.inputs'

    name = fields.Char('Description', related='rule_input_id.name', size=256, required=True)
    rule_input_id = fields.Many2one('hr.rule.input', 'Rule input', required=True, ondelete='cascade', index=True)
    amount = fields.Integer('Amount', required=True, index=True)
    contract_id = fields.Many2one('hr.contract', 'Contract', required=True)
    

class HrContract(models.Model):
    _inherit = 'hr.contract'
    
    input_values_ids = fields.One2many('hr.contract.inputs', 'contract_id', 'Input values')
    seniority_bonus = fields.Integer(string='Seniority bonus', compute='_get_seniority_bonus')
    sal_gross = fields.Integer('Gross Salary', compute="_get_sal_gross", store=True)
    seniority_base_amount = fields.Integer('Seniority base Amount', compute="get_seniority_base_compute", store=True)
    category_id = fields.Many2one('hr.employee.category', string='Category', tracking=True)
    echelon_id = fields.Many2one('hr.paie.echelon', string='Echelon', tracking=True)

    @api.depends('employee_id.category_id')
    def get_seniority_base_compute(self):
        for contract in self :
            grid_line_obj = self.env['hr.paie.grid.line']
            echelon_id = self.env.ref('primetech_rh.grille_sal_echel_A').id
            category_id = self.employee_id.except_cat and self.env.ref('primetech_rh.grille_sal_cat_12') or contract.employee_id.category_id
            grid_line_ids = grid_line_obj.search([('category_id', '=', contract.category_id.id), ('echelon_id', '=', echelon_id)])

            contract.seniority_base_amount = grid_line_ids.sal_base or 0
    
    def _get_seniority_bonus(self):
        contracts = self.env['hr.contract'].search([])
        for contract in contracts:
            first = self.env['hr.contract'].search([('employee_id', '=', contract.employee_id.id)], order='date_start asc', limit=1)
            date_start = first.date_start or False
            today = date.today()
            date_end = contract.date_end and (contract.date_end > today and today or contract.date_end) or today
            
            if date_end < date_start:
                contract.seniority_bonus = 0
            else:
                months = (date_end.year - date_start.year) * 12 + date_end.month - date_start.month + 1
                contract.seniority_bonus = months >= 24 and contract.seniority_base_amount * 0.02 * int(months / 12) or 0

    @api.depends('wage', 'input_values_ids', 'seniority_bonus')
    def _get_sal_gross(self):
        for contract in self:
            gross = contract.wage + sum([input.amount for input in contract.input_values_ids]) + contract.seniority_bonus
            contract.sal_gross = gross


    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            grid = self.env['hr.paie.grid'].search([('state', '=', 'active')])
            wage = 0
            if len(grid) > 0:
                grid_line = grid[0].line_ids.filtered(lambda g: g.category_id == self.employee_id.category_id and g.echelon_id == self.employee_id.echelon_id)
                if len(grid_line) > 0:
                    wage = grid_line[0].sal_base
            self.wage = wage
            self.category_id = self.employee_id.category_id.id
            self.echelon_id = self.employee_id.echelon_id.id

    def write(self, vals):
        """
        This function write an entry in the openchatter whenever we change important information
        on the contract like the model, the drive, the state of the contract or its license plate
        """
        for contract in self:
            changes = []
            if 'wage' in vals and contract.wage != vals['wage']:
                changes.append(_("Base salary: from '%s' to '%s'") % (contract.wage, vals['wage']))
            if 'input_values_ids' in vals:
                for input_val in vals['input_values_ids']:
                    if input_val[0] == 0:                        
                        inpt = self.env['hr.rule.input'].browse(input_val[2]['rule_input_id'])
                        changes.append(_("Indemnity added '%s' amount '%s'") % (inpt[0].name, input_val[2]['amount']))
                    if input_val[0] == 1:
                        inputs = self.env['hr.contract.inputs'].browse(input_val[1])
                        inpt = 'name' in input_val[2] and self.env['hr.rule.input'].browse(input_val[2]['rule_input_id']) or False
                        amount = 'amount' in input_val[2] and input_val[2]['amount'] or inputs[0].amount
                        name = 'name' in input_val[2] and inpt[0].name or inputs[0].name
                        changes.append(_("Indemnity: from '%s'('%s') to '%s'('%s')") % (inputs[0].name, inputs[0].amount, name, amount))
                    if input_val[0] == 2:
                        inputs = self.env['hr.contract.inputs'].browse(input_val[1])
                        changes.append(_("Indemnity deleted '%s'('%s')") % (inputs[0].name, inputs[0].amount))

            if len(changes) > 0:
                self.message_post(body=", ".join(changes))

            return super(HrContract, self).write(vals)
