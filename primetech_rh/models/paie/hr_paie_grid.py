# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class hr_paie_grid_line(models.Model):
    _name = "hr.paie.grid.line"

    category_id = fields.Many2one('hr.employee.category', string="Category", required=True)
    echelon_id = fields.Many2one('hr.paie.echelon', string="Echelon", required=True)
    grid_id = fields.Many2one('hr.paie.grid', string="Salary grid")
    sal_base = fields.Integer('Base salary')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.ref('base.main_company').id)
    
    _sql_constraints = [
        ('grid_category_echelon_uniq', 'unique(category_id, echelon_id, grid_id)', 'A Salary Grid line has already been recorded for this Category and this Echelon, in this same grid on the system!'),
    ]


class hr_paie_grid(models.Model):
    _name = "hr.paie.grid"
    _description = "Salary Grid"

    name = fields.Char(string='Label', required=True)
    version = fields.Char(string='Version')
    date_start = fields.Date(string='Date start', required=True)
    date_end = fields.Date(string='Date end')
    line_ids = fields.One2many('hr.paie.grid.line', 'grid_id', string='Lines')
    state = fields.Selection([('active', 'Actif'), ('inactive', 'Inactif')], string="State", required=True, default='inactive')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.ref('base.main_company').id)

    def set_active(self):
        activ_grid = self.env['hr.paie.grid'].search([('state', '=', 'active')])
        if len(activ_grid) > 0:
            raise ValidationError(_('Error ! You can\'t have more than one active grid.'))
        if len(self.line_ids) > 0:
            self.state = 'active'
        else:
            raise ValidationError(_('Error ! You must fill in the Grid Rows before performing this operation.'))

    def set_inactive(self):
        if self.date_end:
            self.state = 'inactive'
        else:
            raise ValidationError(_('Warning ! You must indicate the end date before performing this operation.'))
