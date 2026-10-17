# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _
from datetime import date, datetime
from odoo.exceptions import UserError, AccessError, ValidationError
from dateutil.relativedelta import relativedelta


class HrPaiExercice(models.Model):
    _name = 'hr.pai.exercice'
    _description = "Payroll fiscal year"

    name = fields.Char('Name', required=True)
    code = fields.Char('Code', size=6, required=True)
    date_start = fields.Date('Date start', required=True)
    date_stop = fields.Date('Date stop', required=True)
    state = fields.Selection([('draft', 'Open'), ('close', 'Closed')], string='State', default='draft')
    period_ids = fields.One2many('hr.pai.period', 'exercice_id', string='Periods')

    def _get_exercice(self, date):
        exercice = self.search([('date_start', '<=', date), ('date_stop', '>=', date), ('state', '=', 'draft')])
        return exercice

    def _exercice_default_get(self):
        date = fields.Date.today()
        exercice = self.search([('date_start', '<=', date), ('date_stop', '>=', date), ('state', '=', 'draft')])
        return exercice

    @api.constrains('date_start', 'date_stop')
    def _check_duration(self):
        for exercice in self:
            if exercice.date_start >= exercice.date_stop:
                raise ValidationError(_('Error!\nThe start date of a exercice must precede its end date.'))
    
    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The code must be unique!'),
    ]

    def action_close(self):
        if self.test_close():
            self.state = 'close'
        else:
            raise ValidationError(_('Error!\nYou cannot close a payroll fiscal year with open periods.'))


    def test_close(self):
        for exercice in self:
            for period in exercice.period_ids:
                if period.state != 'close':
                    return False
            return True

    def generate_periods(self):
        period_obj = self.env['hr.pai.period']
        if len(self.period_ids) > 0:
            self.period_ids.unlink()
        ds = fields.Date.to_date(self.date_start)
        while ds < self.date_stop:
            de = ds + relativedelta(months=1, days=-1)
            if de > self.date_stop:
                de = self.date_stop
            period_obj.create({
                'name' : de.strftime('%m/%Y'),
                'code' : de.strftime('%m/%Y'),
                'date_start': ds.strftime('%Y-%m-%d'),
                'date_stop': de.strftime('%Y-%m-%d'),
                'exercice_id': self.id,
            })
            ds = ds + relativedelta(months=1)
        return True


class HrPaiPeriod(models.Model):
    _name = 'hr.pai.period'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code', size=10, required=True)
    date_start = fields.Date('Date start', required=True)
    date_stop = fields.Date('Date stop', required=True)
    state = fields.Selection([('draft', 'Open'), ('close', 'Closed')], string='State', default='draft')
    exercice_id = fields.Many2one('hr.pai.exercice', string='Pay Exercice', required=True)
    is_13month = fields.Boolean("It's 13th Month?", default=False, required=True)

    @api.constrains('date_start', 'date_stop')
    def _check_duration(self):
        for period in self:
            if period.date_start >= period.date_stop:
                raise ValidationError(_('Error!\nThe start date of a period must precede its end date.'))

    @api.constrains('date_start', 'date_stop')
    def _check_year_limit(self):
        for period in self:
            if period.exercice_id.date_stop < period.date_stop or \
               period.exercice_id.date_stop < period.date_start or \
               period.exercice_id.date_start > period.date_start or \
               period.exercice_id.date_start > period.date_stop:
                raise ValidationError(_('Error!\nThe period is invalid. Either some periods are overlapping or the period\'s dates are not matching the scope of the fiscal year.'))
    
    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The code must be unique!'),
    ]

    def get_next(self, period):
        date_start = fields.Date.to_date(period.date_start)
        next_start = date_start + relativedelta(months=1)
        next_period = self.env['hr.pai.period'].search([('date_start', '=', next_start.strftime('%Y-%m-%d'))])
        return next_period

    def action_close(self):
        self.state = 'close'
