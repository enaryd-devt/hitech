# -*- coding: utf-8 -*-
"""Daily attendance analysis built from the biometric punches."""
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

_logger = logging.getLogger(__name__)

STATUSES = [
    ('pending', 'Pas encore arrivé'),
    ('absent', 'Absent'),
    ('leave', 'Congé'),
    ('holiday', 'Jour férié'),
    ('present', 'Présent'),
    ('late', 'En retard'),
    ('incomplete', 'Pointage incomplet'),
    ('extra', 'Travail hors horaire'),
]
PRESENT_STATUSES = ('present', 'late', 'incomplete', 'extra')
IN_PUNCH_TYPES = ('0', '3', '4')
OUT_PUNCH_TYPES = ('1', '2', '5')


def float_to_hhmm(value):
    if value is False or value is None:
        return ''
    minutes = int(round(value * 60))
    return '%02d:%02d' % divmod(minutes, 60)


def _float_to_time(value):
    minutes = min(int(round(value * 60)), 24 * 60 - 1)
    return time(minutes // 60, minutes % 60)


class BiometricAttendanceDay(models.Model):
    _name = 'biometric.attendance.day'
    _description = 'Journée de présence'
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employé', required=True,
                                  ondelete='cascade', index=True)
    department_id = fields.Many2one('hr.department', string='Département', index=True)
    company_id = fields.Many2one('res.company', string='Société', index=True)
    date = fields.Date(string='Date', required=True, index=True)
    schedule_id = fields.Many2one('biometric.attendance.schedule', string='Horaire',
                                  ondelete='set null')
    plan_source = fields.Selection([
        ('schedule', 'Horaire de pointage'), ('calendar', 'Heures de travail Odoo'),
        ('none', 'Jour non travaillé'),
    ], string='Référence horaire', default='none')
    planned_start = fields.Float(string='Arrivée prévue')
    planned_end = fields.Float(string='Départ prévu')
    planned_hours = fields.Float(string='Heures prévues')
    arrival = fields.Datetime(string='Arrivée')
    departure = fields.Datetime(string='Départ')
    arrival_time = fields.Float(string='Heure d’arrivée')
    departure_time = fields.Float(string='Heure de départ')
    punch_count = fields.Integer(string='Pointages')
    punch_ids = fields.One2many('zk.machine.attendance', 'day_id', string='Pointages du jour')
    worked_hours = fields.Float(string='Heures travaillées')
    late_minutes = fields.Integer(string='Retard (min)')
    early_leave_minutes = fields.Integer(string='Départ anticipé (min)')
    overtime_minutes = fields.Integer(string='Heures sup. (min)')
    is_late = fields.Boolean(string='En retard')
    is_early_leave = fields.Boolean(string='Départ anticipé')
    missing_check_in = fields.Boolean(string='Entrée manquante')
    missing_check_out = fields.Boolean(string='Sortie manquante')
    outside_window = fields.Boolean(string='Hors période autorisée')
    status = fields.Selection(STATUSES, string='Statut', required=True, default='absent',
                              index=True)
    anomaly = fields.Char(string='Observations')
    justified = fields.Boolean(string='Justifié')
    justification_note = fields.Text(string='Justification')
    justified_by = fields.Many2one('res.users', string='Justifié par', readonly=True)
    justified_on = fields.Datetime(string='Justifié le', readonly=True)
    hr_attendance_ids = fields.One2many('hr.attendance', 'biometric_day_id',
                                        string='Présences Odoo générées')
    attendance_sync_message = fields.Char(string='Génération des présences', readonly=True)
    color = fields.Integer(compute='_compute_color')

    _sql_constraints = [
        ('employee_date_unique', 'unique(employee_id, date)',
         'Une seule journée de présence par employé et par date.'),
    ]

    @api.depends('employee_id', 'date')
    def _compute_display_name(self):
        for day in self:
            day.display_name = '%s - %s' % (
                day.employee_id.name or '', day.date and fields.Date.to_string(day.date) or '')

    @api.depends('status')
    def _compute_color(self):
        colors = {'present': 10, 'late': 2, 'incomplete': 3, 'absent': 1, 'pending': 0,
                  'leave': 4, 'holiday': 7, 'extra': 8}
        for day in self:
            day.color = colors.get(day.status, 0)

    # ------------------------------------------------------------------
    # Justification
    # ------------------------------------------------------------------
    def write(self, vals):
        if 'justified' in vals:
            vals = dict(vals)
            if vals['justified']:
                vals.update(justified_by=self.env.uid, justified_on=fields.Datetime.now())
            else:
                vals.update(justified_by=False, justified_on=False)
        return super().write(vals)

    def action_justify(self):
        self.write({'justified': True})
        return True

    def action_unjustify(self):
        self.write({'justified': False})
        return True

    def action_recompute(self):
        self._recompute_employee_dates(self._as_employee_dates())
        return True

    def action_add_punch(self):
        self.ensure_one()
        tz = pytz.timezone(self.employee_id._get_biometric_tz())
        default_hour = self.planned_start if not self.arrival else (self.planned_end or 17.0)
        local = tz.localize(datetime.combine(self.date, _float_to_time(default_hour or 8.0)))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ajouter un pointage'),
            'res_model': 'zk.machine.attendance',
            'view_mode': 'form',
            'views': [(self.env.ref(
                'primetech_biometric_attendance.zk_machine_attendance_view_form_manual').id, 'form')],
            'target': 'new',
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_source': 'manual',
                'default_punching_time': fields.Datetime.to_string(
                    local.astimezone(pytz.utc).replace(tzinfo=None)),
            },
        }

    def _as_employee_dates(self):
        result = defaultdict(set)
        for day in self:
            result[day.employee_id].add(day.date)
        return result

    # ------------------------------------------------------------------
    # Analysis engine
    # ------------------------------------------------------------------
    @api.model
    def _recompute_period(self, date_from, date_to, employees=None):
        """Analyse every tracked employee (and every employee with punches)."""
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        Employee = self.env['hr.employee'].sudo()
        if employees is None:
            employees = Employee.search([('biometric_tracked', '=', True)])
            margin = timedelta(days=1)
            punch_employees = self.env['zk.machine.attendance'].sudo().search([
                ('punching_time', '>=', datetime.combine(date_from - margin, time.min)),
                ('punching_time', '<', datetime.combine(date_to + margin * 2, time.min)),
            ]).employee_id
            employees |= punch_employees
        employee_dates = {}
        current = date_from
        days = []
        while current <= date_to:
            days.append(current)
            current += timedelta(days=1)
        for employee in employees:
            employee_dates[employee] = set(days)
        self._recompute_employee_dates(employee_dates)
        return sum(len(dates) for dates in employee_dates.values())

    @api.model
    def _recompute_employee_dates(self, employee_dates):
        for employee, dates in employee_dates.items():
            for day in sorted(dates):
                try:
                    with self.env.cr.savepoint():
                        self._recompute_one(employee.sudo(), day)
                except Exception:  # keep analysing the other days
                    _logger.exception('Biometric day analysis failed for %s on %s',
                                      employee.display_name, day)

    def _local_float(self, tz, value):
        local = pytz.utc.localize(value).astimezone(tz)
        return local.hour + local.minute / 60.0 + local.second / 3600.0

    def _utc(self, tz, day, hour):
        local = tz.localize(datetime.combine(day, _float_to_time(hour)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _recompute_one(self, employee, day):
        tz_name, plan = employee._get_biometric_day_plan(day)
        tz = pytz.timezone(tz_name or 'UTC')
        now_local = datetime.now(pytz.utc).astimezone(tz)
        if day > now_local.date():
            return
        start_utc = tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = tz.localize(datetime.combine(day + timedelta(days=1), time.min)).astimezone(
            pytz.utc).replace(tzinfo=None)
        punches = self.env['zk.machine.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('punching_time', '>=', start_utc),
            ('punching_time', '<', end_utc),
        ], order='punching_time, id')
        record = self.sudo().search([('employee_id', '=', employee.id), ('date', '=', day)])
        if not punches and (not plan or not employee.biometric_tracked or not employee.active
                            or day < self._tracking_start_date(employee, tz)):
            if record and not record.justified:
                record.hr_attendance_ids.unlink()
                record.unlink()
            return
        vals, roles, intervals = self._analyse(employee, day, tz, plan, punches, now_local)
        if record:
            record.write(vals)
        else:
            record = self.sudo().create(dict(vals, employee_id=employee.id, date=day))
        stale = record.punch_ids - punches
        if stale:
            stale.write({'day_id': False, 'punch_role': False})
        by_role = defaultdict(lambda: self.env['zk.machine.attendance'].sudo())
        for punch in punches:
            by_role[roles.get(punch.id)] |= punch
        for role, role_punches in by_role.items():
            role_punches.write({'day_id': record.id, 'punch_role': role})
        if employee.company_id.biometric_generate_attendance:
            record._sync_hr_attendance(intervals, day == now_local.date())

    def _tracking_start_date(self, employee, tz):
        """First day an absence can be reported: first punch or device enrolment."""
        first_punch = self.env['zk.machine.attendance'].sudo().search(
            [('employee_id', '=', employee.id)], order='punching_time', limit=1)
        if first_punch:
            return pytz.utc.localize(first_punch.punching_time).astimezone(tz).date()
        enrolments = self.env['biometric.device.user'].sudo().search(
            [('employee_id', '=', employee.id)], order='create_date', limit=1)
        if enrolments:
            return pytz.utc.localize(enrolments.create_date).astimezone(tz).date()
        return fields.Date.today() + timedelta(days=1)

    def _build_intervals(self, valid, mode, plan, tz):
        """Group the valid punches of a day into (check-in, check-out) intervals."""
        if not valid:
            return []
        if mode == 'pairs':
            return [(valid[index], valid[index + 1] if index + 1 < len(valid) else None)
                    for index in range(0, len(valid), 2)]
        if mode == 'device':
            intervals, current_in = [], None
            for punch in valid:
                if punch.punch_type in IN_PUNCH_TYPES:
                    kind = 'in'
                elif punch.punch_type in OUT_PUNCH_TYPES:
                    kind = 'out'
                else:
                    kind = 'out' if current_in else 'in'
                if kind == 'in':
                    if current_in:
                        intervals.append((current_in, None))
                    current_in = punch
                else:
                    intervals.append((current_in, punch))
                    current_in = None
            if current_in:
                intervals.append((current_in, None))
            return intervals
        if len(valid) >= 2:
            return [(valid[0], valid[-1])]
        punch = valid[0]
        if plan and plan['enforce_windows']:
            value = self._local_float(tz, punch.punching_time)
            in_from, in_until = plan['check_in_window']
            out_from, out_until = plan['check_out_window']
            if out_from <= value <= out_until and not in_from <= value <= in_until:
                return [(None, punch)]
        return [(punch, None)]

    def _leave_status(self, employee, day, tz, plan):
        """Return (status, covers_start, covers_end) for leaves overlapping the plan."""
        if not plan:
            return False, False, False
        start = self._utc(tz, day, plan['start'])
        end = self._utc(tz, day, plan['end'])
        calendar_ids = [False] + employee.resource_calendar_id.ids
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('date_from', '<', end), ('date_to', '>', start),
            ('time_type', '=', 'leave'),
            ('company_id', 'in', [False, employee.company_id.id]),
            '|', ('resource_id', '=', employee.resource_id.id),
            '&', ('resource_id', '=', False), ('calendar_id', 'in', calendar_ids),
        ])
        if not leaves:
            return False, False, False
        covered = sum(
            (min(leave.date_to, end) - max(leave.date_from, start)).total_seconds()
            for leave in leaves)
        covers_start = any(leave.date_from <= start < leave.date_to for leave in leaves)
        covers_end = any(leave.date_from < end <= leave.date_to for leave in leaves)
        status = False
        if covered >= (end - start).total_seconds() / 2.0:
            status = 'holiday' if all(not leave.resource_id for leave in leaves) else 'leave'
        return status, covers_start, covers_end

    def _analyse(self, employee, day, tz, plan, punches, now_local):
        company = employee.company_id
        min_gap = timedelta(minutes=max(0, company.biometric_min_punch_interval))
        roles, valid, last = {}, [], None
        for punch in punches:
            if not punch.method_allowed:
                roles[punch.id] = 'unauthorized'
                continue
            if last and punch.punching_time - last.punching_time < min_gap:
                roles[punch.id] = 'duplicate'
                continue
            valid.append(punch)
            last = punch
        is_today = day == now_local.date()
        intervals = self._build_intervals(valid, company.biometric_punch_mode, plan, tz)
        for punch in valid:
            roles[punch.id] = 'intermediate'
        for check_in, check_out in intervals:
            if check_in:
                roles[check_in.id] = 'in'
            if check_out:
                roles[check_out.id] = 'out'

        arrival = intervals[0][0] if intervals else None
        departure = intervals[-1][1] if intervals else None
        missing_in = any(not check_in for check_in, _out in intervals)
        open_intervals = [check_in for check_in, check_out in intervals if not check_out]
        if is_today and intervals and not intervals[-1][1]:
            open_intervals = open_intervals[:-1]
        missing_out = bool(open_intervals)

        worked = 0.0
        for check_in, check_out in intervals:
            if not (check_in and check_out):
                continue
            duration = (check_out.punching_time - check_in.punching_time).total_seconds() / 3600.0
            if (company.biometric_punch_mode == 'first_last' and plan
                    and plan['break_end'] > plan['break_start']):
                in_value = self._local_float(tz, check_in.punching_time)
                out_value = self._local_float(tz, check_out.punching_time)
                overlap = min(out_value, plan['break_end']) - max(in_value, plan['break_start'])
                duration -= max(0.0, overlap)
            worked += max(0.0, duration)

        leave_status, leave_covers_start, leave_covers_end = self._leave_status(
            employee, day, tz, plan)
        arrival_value = self._local_float(tz, arrival.punching_time) if arrival else False
        departure_value = self._local_float(tz, departure.punching_time) if departure else False
        late = early = overtime = 0
        outside = False
        notes = []
        if plan:
            if arrival and not leave_covers_start:
                delay = (arrival_value - plan['start']) * 60.0
                if delay > plan['grace']:
                    late = int(round(delay if plan['late_mode'] == 'from_start'
                                     else delay - plan['grace']))
            # Today, the last punch is only a departure once the planned end is reached.
            day_over = not is_today or now_local.hour + now_local.minute / 60.0 >= plan['end']
            if departure and day_over and not leave_covers_end:
                early_value = (plan['end'] - departure_value) * 60.0
                if early_value > plan['early_tolerance']:
                    early = int(round(early_value))
                extra = (departure_value - plan['end']) * 60.0
                if extra > plan['overtime_threshold']:
                    overtime = int(round(extra))
            if plan['enforce_windows']:
                in_from, in_until = plan['check_in_window']
                out_from, out_until = plan['check_out_window']
                if arrival and not in_from <= arrival_value <= in_until:
                    outside = True
                    roles[arrival.id] = 'outside'
                if departure and not out_from <= departure_value <= out_until:
                    outside = True
                    roles[departure.id] = 'outside'
        elif valid:
            overtime = int(round(worked * 60))

        if not valid:
            if leave_status:
                status = leave_status
            elif is_today and now_local.hour + now_local.minute / 60.0 < (
                    plan['start'] + plan['grace'] / 60.0):
                status = 'pending'
            else:
                status = 'absent'
        elif not plan:
            status = 'extra'
            notes.append(_('Pointage un jour non travaillé'))
        elif missing_in or missing_out:
            status = 'incomplete'
        elif late:
            status = 'late'
        else:
            status = 'present'
        if leave_status and valid:
            notes.append(dict(STATUSES)[leave_status])
        if late:
            notes.append(_('Retard de %s min', late))
        if early:
            notes.append(_('Départ anticipé de %s min', early))
        if overtime and plan:
            notes.append(_('%s min après l’heure de départ', overtime))
        if missing_in:
            notes.append(_('Entrée non pointée'))
        if missing_out:
            notes.append(_('Sortie non pointée'))
        if outside:
            notes.append(_('Pointage hors période autorisée'))

        vals = {
            'department_id': employee.department_id.id,
            'company_id': employee.company_id.id,
            'schedule_id': plan and plan['schedule_id'] or False,
            'plan_source': plan['source'] if plan else 'none',
            'planned_start': plan['start'] if plan else 0.0,
            'planned_end': plan['end'] if plan else 0.0,
            'planned_hours': plan['planned_hours'] if plan else 0.0,
            'arrival': arrival.punching_time if arrival else False,
            'departure': departure.punching_time if departure else False,
            'arrival_time': arrival_value or 0.0,
            'departure_time': departure_value or 0.0,
            'punch_count': len(valid),
            'worked_hours': round(worked, 4),
            'late_minutes': late,
            'early_leave_minutes': early,
            'overtime_minutes': overtime,
            'is_late': bool(late),
            'is_early_leave': bool(early),
            'missing_check_in': missing_in,
            'missing_check_out': missing_out,
            'outside_window': outside,
            'status': status,
            'anomaly': ' · '.join(notes),
        }
        return vals, roles, intervals

    def _sync_hr_attendance(self, intervals, is_today):
        """Mirror the analysed intervals into hr.attendance records."""
        self.ensure_one()
        wanted = []
        for index, (check_in, check_out) in enumerate(intervals):
            if not check_in:
                continue
            if not check_out and not (is_today and index == len(intervals) - 1):
                continue
            wanted.append((check_in.punching_time, check_out.punching_time if check_out else False))
        existing = self.hr_attendance_ids.sorted('check_in')
        current = [(attendance.check_in, attendance.check_out or False) for attendance in existing]
        if current == wanted:
            return
        try:
            with self.env.cr.savepoint():
                existing.sudo().unlink()
                self.env['hr.attendance'].sudo().create([{
                    'employee_id': self.employee_id.id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'in_mode': 'biometric',
                    'out_mode': 'biometric',
                    'biometric_day_id': self.id,
                } for check_in, check_out in wanted])
            message = False
        except (ValidationError, UserError) as error:
            message = str(error.args[0] if error.args else error)[:500]
        if message != (self.attendance_sync_message or False):
            self.sudo().write({'attendance_sync_message': message})

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------
    @api.model
    def cron_analyse_days(self):
        """Refresh today (absences, late arrivals) and finalise yesterday."""
        today = fields.Date.context_today(self)
        self._recompute_period(today - timedelta(days=1), today)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def action_dashboard_refresh(self, date_str=False):
        devices = self.env['biometric.device.details'].search(
            [('active', '=', True), ('connection_mode', '=', 'direct')])
        for device in devices:
            try:
                with self.env.cr.savepoint():
                    device._run_synchronization()
            except Exception as error:  # the dashboard shows the device error
                _logger.warning('Dashboard synchronization failed for %s: %s',
                                device.display_name, error)
        today = fields.Date.context_today(self)
        target = fields.Date.to_date(date_str) if date_str else today
        self._recompute_period(min(target, today), min(target, today))
        return self.get_dashboard_data(date_str)

    def _employee_payload(self, day):
        return {
            'id': day.id,
            'employee_id': day.employee_id.id,
            'name': day.employee_id.name,
            'department': day.department_id.name or '',
            'arrival': float_to_hhmm(day.arrival_time) if day.arrival else '',
            'departure': float_to_hhmm(day.departure_time) if day.departure else '',
            'planned_start': float_to_hhmm(day.planned_start) if day.plan_source != 'none' else '',
            'late_minutes': day.late_minutes,
            'justified': day.justified,
            'anomaly': day.anomaly or '',
        }

    @api.model
    def get_dashboard_data(self, date_str=False):
        today = fields.Date.context_today(self)
        day = fields.Date.to_date(date_str) if date_str else today
        company_ids = self.env.companies.ids
        base_domain = [('company_id', 'in', company_ids)]
        days = self.search(expression.AND([base_domain, [('date', '=', day)]]))
        tracked = self.env['hr.employee'].search_count([
            ('biometric_tracked', '=', True), ('company_id', 'in', company_ids)])

        def by_status(*statuses):
            return days.filtered(lambda record: record.status in statuses)

        present = by_status(*PRESENT_STATUSES)
        late = days.filtered('is_late')
        expected = days.filtered(lambda record: record.plan_source != 'none'
                                 and record.status not in ('leave', 'holiday'))
        month_start = day.replace(day=1)
        month_domain = expression.AND([base_domain, [
            ('date', '>=', month_start), ('date', '<=', day)]])
        month_present = self.search_count(expression.AND([
            month_domain, [('status', 'in', PRESENT_STATUSES), ('plan_source', '!=', 'none')]]))
        month_late = self._read_group(
            expression.AND([month_domain, [('is_late', '=', True)]]),
            ['employee_id'], ['__count', 'late_minutes:sum'],
            order='late_minutes:sum desc')
        month_late_count = sum(count for _employee, count, _minutes in month_late)
        month_late_minutes = sum(minutes for _employee, _count, minutes in month_late)
        month_absent = self.search_count(expression.AND([
            month_domain, [('status', '=', 'absent'), ('justified', '=', False)]]))

        trend_start = day - timedelta(days=13)
        trend_groups = self._read_group(
            expression.AND([base_domain, [('date', '>=', trend_start), ('date', '<=', day)]]),
            ['date:day', 'status'], ['__count'])
        trend_map = defaultdict(lambda: defaultdict(int))
        for group_day, status, count in trend_groups:
            trend_map[fields.Date.to_date(group_day)][status] += count
        trend = []
        for offset in range(14):
            current = trend_start + timedelta(days=offset)
            counts = trend_map.get(current, {})
            trend.append({
                'date': fields.Date.to_string(current),
                'label': current.strftime('%d/%m'),
                'present': sum(counts.get(status, 0) for status in ('present', 'extra', 'incomplete')),
                'late': counts.get('late', 0),
                'absent': counts.get('absent', 0),
                'leave': counts.get('leave', 0) + counts.get('holiday', 0),
            })

        departments = defaultdict(lambda: {'name': '', 'expected': 0, 'present': 0, 'late': 0})
        for record in days:
            entry = departments[record.department_id.id or 0]
            entry['name'] = record.department_id.name or _('Sans département')
            entry['department_id'] = record.department_id.id or False
            if record in expected:
                entry['expected'] += 1
            if record in present:
                entry['present'] += 1
            if record.is_late:
                entry['late'] += 1

        devices = []
        now = fields.Datetime.now()
        for device in self.env['biometric.device.details'].search([('active', '=', True)]):
            last_contact = device.last_contact_at
            online = bool(last_contact and (now - last_contact) <= timedelta(
                minutes=max(device.sync_interval, 1) * 3 + 2))
            devices.append({
                'id': device.id,
                'name': device.name,
                'ip': device.device_ip,
                'online': online,
                'state': device.last_sync_state,
                'last_sync': fields.Datetime.context_timestamp(self, device.last_sync_at).strftime(
                    '%d/%m/%Y %H:%M') if device.last_sync_at else '',
                'message': device.last_sync_message or '',
                'users': device.info_user_count,
                'records': device.info_record_count,
            })

        recent_punches = self.env['zk.machine.attendance'].search([
            ('company_id', 'in', company_ids),
            ('punching_time', '>=', fields.Datetime.now() - timedelta(hours=24)),
        ], limit=8)

        to_fix = self.search_count(expression.AND([month_domain, [
            ('justified', '=', False), '|', '|', ('missing_check_in', '=', True),
            ('missing_check_out', '=', True), ('outside_window', '=', True)]]))
        is_manager = self.env.user.has_group('hr_attendance.group_hr_attendance_manager')
        unmapped_users = self.env['biometric.device.user'].search_count(
            [('employee_id', '=', False)]) if is_manager else 0

        return {
            'date': fields.Date.to_string(day),
            'date_label': day.strftime('%d/%m/%Y'),
            'is_today': day == today,
            'is_manager': is_manager,
            'counters': {
                'to_fix': to_fix,
                'unjustified_absences': month_absent,
                'unmapped_users': unmapped_users,
                'devices': len(devices),
                'schedules': self.env['biometric.attendance.schedule'].search_count([]),
            },
            'kpis': {
                'tracked': tracked,
                'expected': len(expected),
                'present': len(present),
                'late': len(late),
                'late_unjustified': len(late.filtered(lambda record: not record.justified)),
                'absent': len(by_status('absent')),
                'pending': len(by_status('pending')),
                'leave': len(by_status('leave', 'holiday')),
                'incomplete': len(by_status('incomplete')),
                'late_minutes': sum(late.mapped('late_minutes')),
                'worked_hours': round(sum(days.mapped('worked_hours')), 1),
                'attendance_rate': round(100.0 * len(present & expected) / len(expected)) if expected else 0,
                'month_late_count': month_late_count,
                'month_late_minutes': month_late_minutes,
                'month_absent': month_absent,
                'month_punctuality': round(100.0 * (month_present - month_late_count) / month_present)
                if month_present else 0,
            },
            'late': [self._employee_payload(record) for record in late.sorted(
                lambda record: -record.late_minutes)],
            'absent': [self._employee_payload(record) for record in by_status('absent')],
            'pending': [self._employee_payload(record) for record in by_status('pending')],
            'incomplete': [self._employee_payload(record) for record in by_status('incomplete')],
            'top_late': [{
                'employee_id': employee.id,
                'name': employee.name,
                'count': count,
                'minutes': minutes,
            } for employee, count, minutes in month_late[:8]],
            'trend': trend,
            'departments': sorted(departments.values(), key=lambda entry: entry['name']),
            'devices': devices,
            'recent_punches': [{
                'name': punch.employee_id.name,
                'time': fields.Datetime.context_timestamp(self, punch.punching_time).strftime(
                    '%d/%m %H:%M'),
                'device': punch.device_id.name or _('Saisie manuelle'),
            } for punch in recent_punches],
        }
