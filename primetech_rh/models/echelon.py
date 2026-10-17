# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _


class hr_paie_echelon(models.Model):

    _name = "hr.paie.echelon"
    _description = "Echelon"
    _order       = "sequence asc"
    _auto        = True
    
    name = fields.Char(string='Label',size=2,required=True)
    note = fields.Text(string='Description',required=False)
    sequence = fields.Integer('Sequence', required=True)
    active = fields.Boolean(string='Active', default=True, help="Allows you to deactivate the item without deleting it!")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.ref('base.main_company').id)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists !"),
    ]


class hr_employee_category(models.Model):

    _name       = "hr.employee.category"
    _auto        = True
    _order       = "sequence asc"
    _inherit    = ['hr.employee.category']

    sequence = fields.Integer('Sequence', required=True)