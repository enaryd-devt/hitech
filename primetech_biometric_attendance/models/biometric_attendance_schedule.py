# -*- coding: utf-8 -*-
"""Attendance schedules used to analyse biometric punches."""
import pytz

from odoo import Command, api, fields, models, _
from odoo.exceptions import ValidationError

WEEK_DAYS = [
    ('0', 'Lundi'), ('1', 'Mardi'), ('2', 'Mercredi'), ('3', 'Jeudi'),
    ('4', 'Vendredi'), ('5', 'Samedi'), ('6', 'Dimanche'),
]


def _default_window(start, end):
    """Sensible check-in / check-out periods around planned hours."""
    middle = round((start + end) / 2.0 * 4) / 4.0
    return {
        'check_in_from': max(0.0, start - 2.0),
        'check_in_until': middle,
        'check_out_from': middle,
        'check_out_until': min(23.99, end + 5.0),
    }


def _default_line(day, start=8.0, end=17.0, break_start=12.0, break_end=13.0):
    return dict(day_of_week=day, planned_start=start, planned_end=end,
                break_start=break_start, break_end=break_end,
                **_default_window(start, end))


class BiometricAttendanceSchedule(models.Model):
    _name = 'biometric.attendance.schedule'
    _description = 'Horaire de pointage'
    _order = 'sequence, name'

    def _default_line_ids(self):
        return [Command.create(_default_line(day)) for day in '01234']

    name = fields.Char(string='Libellé', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Couleur')
    company_id = fields.Many2one(
        'res.company', string='Société', required=True,
        default=lambda self: self.env.company)
    timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        string='Fuseau horaire', required=True,
        default=lambda self: self.env.user.tz or 'Africa/Douala')
    line_ids = fields.One2many(
        'biometric.attendance.schedule.line', 'schedule_id',
        string='Jours travaillés', copy=True, default=_default_line_ids)
    grace_minutes = fields.Integer(
        string='Tolérance de retard (minutes)', default=10,
        help="Une arrivée dans ce délai après l'heure prévue n'est pas un retard.")
    late_count_mode = fields.Selection([
        ('from_start', "Depuis l'heure prévue"),
        ('after_grace', 'Au-delà de la tolérance'),
    ], string='Calcul du retard', default='from_start', required=True,
        help="Arrivée prévue 08:00, tolérance 10 min, arrivée 08:25 : "
             "25 min de retard depuis l'heure prévue, 15 min au-delà de la tolérance.")
    early_leave_tolerance = fields.Integer(
        string='Tolérance de départ anticipé (minutes)', default=0)
    overtime_threshold = fields.Integer(
        string='Heures sup. à partir de (minutes après la fin)', default=15,
        help="Le temps passé après l'heure de départ prévue n'est compté en "
             "heures supplémentaires qu'au-delà de ce seuil.")
    enforce_windows = fields.Boolean(
        string='Contrôler les périodes de pointage',
        help="Signale les arrivées et départs pointés en dehors des périodes "
             "autorisées de chaque jour.")
    employee_ids = fields.Many2many(
        'hr.employee', string='Employés', compute='_compute_employee_ids',
        inverse='_inverse_employee_ids', context={'active_test': False})
    department_ids = fields.Many2many(
        'hr.department', string='Départements', compute='_compute_department_ids',
        inverse='_inverse_department_ids')
    employee_count = fields.Integer(compute='_compute_employee_ids')
    weekly_hours = fields.Float(string='Heures par semaine', compute='_compute_weekly_hours')
    is_company_default = fields.Boolean(
        string='Horaire par défaut', compute='_compute_is_company_default')

    @api.depends('line_ids.planned_hours')
    def _compute_weekly_hours(self):
        for schedule in self:
            schedule.weekly_hours = sum(schedule.line_ids.mapped('planned_hours'))

    def _compute_employee_ids(self):
        groups = self.env['hr.employee'].with_context(active_test=False)._read_group(
            [('biometric_schedule_id', 'in', self.ids)], ['biometric_schedule_id'], ['id:array_agg'])
        mapping = {schedule.id: ids for schedule, ids in groups}
        for schedule in self:
            schedule.employee_ids = [Command.set(mapping.get(schedule.id, []))]
            schedule.employee_count = len(mapping.get(schedule.id, []))

    def _inverse_employee_ids(self):
        employees = self.env['hr.employee'].with_context(active_test=False)
        for schedule in self:
            current = employees.search([('biometric_schedule_id', '=', schedule.id)])
            (current - schedule.employee_ids).biometric_schedule_id = False
            (schedule.employee_ids - current).biometric_schedule_id = schedule

    def _compute_department_ids(self):
        departments = self.env['hr.department'].search([('biometric_schedule_id', 'in', self.ids)])
        for schedule in self:
            schedule.department_ids = departments.filtered(
                lambda department: department.biometric_schedule_id == schedule)

    def _inverse_department_ids(self):
        for schedule in self:
            current = self.env['hr.department'].search([('biometric_schedule_id', '=', schedule.id)])
            (current - schedule.department_ids).biometric_schedule_id = False
            (schedule.department_ids - current).biometric_schedule_id = schedule

    def _compute_is_company_default(self):
        for schedule in self:
            schedule.is_company_default = schedule.company_id.biometric_default_schedule_id == schedule

    @api.constrains('grace_minutes', 'early_leave_tolerance', 'overtime_threshold')
    def _check_tolerances(self):
        for schedule in self:
            if min(schedule.grace_minutes, schedule.early_leave_tolerance,
                   schedule.overtime_threshold) < 0:
                raise ValidationError(_('Les tolérances ne peuvent pas être négatives.'))

    def action_set_company_default(self):
        self.ensure_one()
        self.company_id.biometric_default_schedule_id = self
        return True

    def action_view_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Employés - %s', self.name),
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('biometric_schedule_id', '=', self.id)],
            'context': {'default_biometric_schedule_id': self.id},
        }

    def action_recalculate(self):
        """Reanalyse the attendance days of the employees using this schedule."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recalculer les présences'),
            'res_model': 'biometric.attendance.recompute.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_line(self, weekday):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.day_of_week == str(weekday))[:1]


class BiometricAttendanceScheduleLine(models.Model):
    _name = 'biometric.attendance.schedule.line'
    _description = 'Jour de travail d’un horaire de pointage'
    _order = 'schedule_id, day_of_week'

    schedule_id = fields.Many2one(
        'biometric.attendance.schedule', string='Horaire', required=True,
        ondelete='cascade', index=True)
    day_of_week = fields.Selection(WEEK_DAYS, string='Jour', required=True, default='0')
    planned_start = fields.Float(string='Arrivée prévue', required=True, default=8.0)
    planned_end = fields.Float(string='Départ prévu', required=True, default=17.0)
    break_start = fields.Float(string='Début de pause', default=12.0)
    break_end = fields.Float(string='Fin de pause', default=13.0)
    check_in_from = fields.Float(string='Arrivée autorisée de', default=6.0)
    check_in_until = fields.Float(string="Arrivée autorisée jusqu'à", default=12.5)
    check_out_from = fields.Float(string='Départ autorisé de', default=12.5)
    check_out_until = fields.Float(string="Départ autorisé jusqu'à", default=22.0)
    planned_hours = fields.Float(string='Heures prévues', compute='_compute_planned_hours', store=True)

    _sql_constraints = [
        ('schedule_day_unique', 'unique(schedule_id, day_of_week)',
         'Un horaire ne peut définir qu’une seule ligne par jour.'),
    ]

    @api.depends('planned_start', 'planned_end', 'break_start', 'break_end')
    def _compute_planned_hours(self):
        for line in self:
            line.planned_hours = max(0.0, line.planned_end - line.planned_start - line._break_duration())

    def _break_duration(self):
        self.ensure_one()
        if self.break_end <= self.break_start:
            return 0.0
        start = max(self.break_start, self.planned_start)
        end = min(self.break_end, self.planned_end)
        return max(0.0, end - start)

    @api.onchange('planned_start', 'planned_end')
    def _onchange_planned_hours(self):
        if self.planned_end > self.planned_start:
            self.update(_default_window(self.planned_start, self.planned_end))

    @api.constrains('planned_start', 'planned_end', 'break_start', 'break_end',
                    'check_in_from', 'check_in_until', 'check_out_from', 'check_out_until')
    def _check_hours(self):
        for line in self:
            values = (line.planned_start, line.planned_end, line.break_start, line.break_end,
                      line.check_in_from, line.check_in_until, line.check_out_from,
                      line.check_out_until)
            if any(value < 0 or value >= 24 for value in values):
                raise ValidationError(_('Les heures doivent être comprises entre 00:00 et 23:59.'))
            if line.planned_end <= line.planned_start:
                raise ValidationError(_("L'heure de départ doit être postérieure à l'heure d'arrivée (%s).",
                                        line.display_name))
            if line.break_end < line.break_start:
                raise ValidationError(_('La fin de pause doit être postérieure à son début.'))
            if line.check_in_until < line.check_in_from or line.check_out_until < line.check_out_from:
                raise ValidationError(_('Chaque période de pointage doit finir après son début.'))

    @api.depends('schedule_id', 'day_of_week')
    def _compute_display_name(self):
        days = dict(WEEK_DAYS)
        for line in self:
            line.display_name = f"{line.schedule_id.name or ''} - {days.get(line.day_of_week, '')}"
