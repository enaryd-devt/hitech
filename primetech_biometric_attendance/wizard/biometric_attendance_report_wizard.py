# -*- coding: utf-8 -*-
"""Reporting centre: attendance, punches, device users and device activity (PDF and Excel)."""
import io
from collections import OrderedDict, defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import xlsxwriter

from ..models.biometric_attendance_day import PRESENT_STATUSES, float_to_hhmm

REPORT_TYPES = [
    ('attendance', 'Rapport de présence'),
    ('punches', 'Pointages'),
    ('users', 'Utilisateurs des pointeuses'),
    ('devices', 'Activité des pointeuses'),
]
DAY_NAMES = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
BRAND = '#5B3FD1'


class BiometricAttendanceReportWizard(models.TransientModel):
    _name = 'biometric.attendance.report.wizard'
    _description = 'Rapports des pointages'

    report_type = fields.Selection(REPORT_TYPES, string='Rapport', required=True, default='attendance')
    date_from = fields.Date(string='Du', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Au', required=True, default=fields.Date.context_today)
    employee_ids = fields.Many2many('hr.employee', string='Employés',
                                    help='Laissez vide pour tous les employés.')
    department_id = fields.Many2one('hr.department', string='Département')
    device_ids = fields.Many2many('biometric.device.details', string='Pointeuses',
                                  help='Laissez vide pour toutes les pointeuses.')
    show_details = fields.Boolean(string='Détail jour par jour', default=True)
    include_duplicates = fields.Boolean(string='Inclure les doublons ignorés')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('La date de début doit précéder la date de fin.'))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tz(self):
        return pytz.timezone(self.env.user.tz or self.env.company.partner_id.tz or 'Africa/Douala')

    def _utc_bounds(self):
        tz = self._tz()
        start = tz.localize(datetime.combine(self.date_from, time.min)).astimezone(pytz.utc)
        end = tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min)).astimezone(pytz.utc)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    def _local(self, value):
        return pytz.utc.localize(value).astimezone(self._tz()) if value else False

    def _employee_domain(self, field='employee_id'):
        domain = []
        if self.employee_ids:
            domain.append((field, 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('%s.department_id' % field, 'child_of', self.department_id.id))
        return domain

    def _devices(self):
        return self.device_ids or self.env['biometric.device.details'].search([])

    def period_label(self):
        return '%s au %s' % (self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y'))

    def filters_label(self):
        parts = []
        if self.department_id:
            parts.append(_('Département : %s', self.department_id.name))
        if self.employee_ids:
            parts.append(_('%s employé(s) sélectionné(s)', len(self.employee_ids)))
        if self.device_ids:
            parts.append(_('Pointeuse(s) : %s', ', '.join(self.device_ids.mapped('name'))))
        return ' · '.join(parts)

    @staticmethod
    def day_label(day):
        return '%s %s' % (DAY_NAMES[day.weekday()], day.strftime('%d/%m/%Y'))

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _get_days(self):
        self.ensure_one()
        domain = [('date', '>=', self.date_from), ('date', '<=', self.date_to),
                  ('company_id', 'in', self.env.companies.ids)] + self._employee_domain()
        return self.env['biometric.attendance.day'].search(domain, order='employee_id, date')

    def _attendance_data(self):
        Day = self.env['biometric.attendance.day']
        per_employee = OrderedDict()
        for day in self._get_days():
            per_employee[day.employee_id] = per_employee.get(day.employee_id, Day) | day
        employees = []
        for employee, days in per_employee.items():
            planned = days.filtered(lambda day: day.plan_source != 'none')
            employees.append({
                'employee': employee,
                'days': days,
                'planned_days': len(planned.filtered(lambda day: day.status not in ('leave', 'holiday'))),
                'present_days': len(days.filtered(lambda day: day.status in PRESENT_STATUSES)),
                'absent_days': len(days.filtered(lambda day: day.status == 'absent')),
                'unjustified_absences': len(days.filtered(lambda day: day.status == 'absent' and not day.justified)),
                'leave_days': len(days.filtered(lambda day: day.status in ('leave', 'holiday'))),
                'late_count': len(days.filtered('is_late')),
                'late_minutes': sum(days.mapped('late_minutes')),
                'early_minutes': sum(days.mapped('early_leave_minutes')),
                'overtime_minutes': sum(days.mapped('overtime_minutes')),
                'incomplete_days': len(days.filtered(lambda day: day.missing_check_in or day.missing_check_out)),
                'worked_hours': sum(days.mapped('worked_hours')),
                'planned_hours': sum(planned.mapped('planned_hours')),
            })
        totals = {key: sum(line[key] for line in employees) for key in (
            'planned_days', 'present_days', 'absent_days', 'late_count', 'late_minutes', 'worked_hours')}
        return {'employees': employees, 'totals': totals}

    def _get_punches(self):
        start, end = self._utc_bounds()
        domain = [('punching_time', '>=', start), ('punching_time', '<', end),
                  ('company_id', 'in', self.env.companies.ids)] + self._employee_domain()
        if self.device_ids:
            domain.append(('device_id', 'in', self.device_ids.ids))
        if not self.include_duplicates:
            domain.append(('punch_role', '!=', 'duplicate'))
        return self.env['zk.machine.attendance'].search(domain, order='punching_time, employee_id')

    def _punches_data(self):
        punches = self._get_punches()
        method = dict(punches._fields['attendance_type'].selection)
        role = dict(punches._fields['punch_role'].selection)
        source = dict(punches._fields['source'].selection)
        rows, per_day = [], OrderedDict()
        for punch in punches:
            local = self._local(punch.punching_time)
            row = {
                'date': local.date(), 'time': local.strftime('%H:%M:%S'),
                'employee': punch.employee_id.name, 'department': punch.department_id.name or '',
                'user_id': punch.device_id_num or '', 'device': punch.device_id.name or _('Saisie manuelle'),
                'method': method.get(punch.attendance_type, ''), 'role': role.get(punch.punch_role, ''),
                'source': source.get(punch.source, ''), 'note': punch.note or '',
            }
            rows.append(row)
            per_day.setdefault(row['date'], []).append(row)
        return {
            'rows': rows, 'per_day': per_day,
            'stats': {
                'total': len(rows),
                'employees': len(set(punches.mapped('employee_id').ids)),
                'days': len(per_day),
                'manual': len(punches.filtered(lambda punch: punch.source == 'manual')),
            },
        }

    def _users_data(self):
        domain = [('device_id', 'in', self._devices().ids)]
        if self.employee_ids or self.department_id:
            domain += self._employee_domain()
        users = self.env['biometric.device.user'].with_context(active_test=False).search(
            domain, order='device_id, device_user_id')
        privilege = dict(users._fields['privilege'].selection)
        state = dict(users._fields['sync_state'].selection)
        rows = [{
            'device': user.device_id.name, 'user_id': user.device_user_id,
            'device_name': user.device_user_name or '', 'employee': user.employee_id.name or '',
            'department': user.department_id.name or '', 'privilege': privilege.get(user.privilege, ''),
            'card': user.card or '', 'state': state.get(user.sync_state, ''), 'state_key': user.sync_state,
            'message': user.sync_message or '', 'active': user.active,
            'last_sync': self._local(user.last_synced_at).strftime('%d/%m/%Y %H:%M') if user.last_synced_at else '',
        } for user in users]
        return {
            'rows': rows,
            'stats': {
                'total': len(rows),
                'mapped': len([row for row in rows if row['employee']]),
                'unmapped': len([row for row in rows if not row['employee']]),
                'errors': len([row for row in rows if row['state_key'] == 'error']),
            },
        }

    def _devices_data(self):
        start, end = self._utc_bounds()
        Punch = self.env['zk.machine.attendance']
        Log = self.env['biometric.sync.log']
        mode = dict(self.env['biometric.device.details']._fields['connection_mode'].selection)
        sync_state = dict(self.env['biometric.device.details']._fields['last_sync_state'].selection)
        devices = []
        for device in self._devices():
            punches = Punch.search([('device_id', '=', device.id), ('punching_time', '>=', start),
                                    ('punching_time', '<', end)])
            per_day = defaultdict(int)
            for punch in punches:
                per_day[self._local(punch.punching_time).date()] += 1
            days, current = [], self.date_from
            while current <= self.date_to:
                days.append({'date': current, 'count': per_day.get(current, 0)})
                current += timedelta(days=1)
            logs = Log.search([('device_id', '=', device.id), ('date', '>=', start), ('date', '<', end)],
                              order='date desc')
            errors = logs.filtered(lambda log: log.state == 'error')
            devices.append({
                'device': device,
                'mode': mode.get(device.connection_mode, ''),
                'sync_state': sync_state.get(device.last_sync_state, ''),
                'last_sync': self._local(device.last_sync_at).strftime('%d/%m/%Y %H:%M') if device.last_sync_at else '',
                'memory': '%s / %s' % (device.info_record_count or 0, device.info_record_capacity or '?'),
                'punches': len(punches),
                'employees': len(set(punches.mapped('employee_id').ids)),
                'days': days,
                'max_day': max([day['count'] for day in days] or [0]) or 1,
                'logs_total': len(logs),
                'logs_errors': len(errors),
                'logs_warnings': len(logs.filtered(lambda log: log.state == 'warning')),
                'last_errors': [{
                    'date': self._local(log.date).strftime('%d/%m/%Y %H:%M'),
                    'operation': dict(log._fields['operation'].selection).get(log.operation, ''),
                    'message': log.message or '',
                } for log in errors[:10]],
            })
        return {'devices': devices}

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    REPORT_ACTIONS = {
        'attendance': 'primetech_biometric_attendance.action_report_biometric_attendance',
        'punches': 'primetech_biometric_attendance.action_report_biometric_punches',
        'users': 'primetech_biometric_attendance.action_report_biometric_users',
        'devices': 'primetech_biometric_attendance.action_report_biometric_devices',
    }

    def _check_not_empty(self):
        self.ensure_one()
        empty = {
            'attendance': lambda: not self._get_days(),
            'punches': lambda: not self._get_punches(),
            'users': lambda: not self._users_data()['rows'],
            'devices': lambda: not self._devices(),
        }[self.report_type]()
        if empty:
            raise UserError(_('Aucune donnée pour ce rapport sur la période et les filtres choisis.'))

    def action_print(self):
        self._check_not_empty()
        return self.env.ref(self.REPORT_ACTIONS[self.report_type]).report_action(self)

    def action_export_xlsx(self):
        self._check_not_empty()
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/primetech_biometric/report/xlsx/%s' % self.id}

    def action_open_analysis(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.biometric_attendance_day_analysis_action')
        action['domain'] = [('id', 'in', self._get_days().ids)]
        return action

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def xlsx_filename(self):
        label = dict(REPORT_TYPES)[self.report_type].lower().replace(' ', '_')
        return '%s_%s_%s.xlsx' % (label, self.date_from.strftime('%Y%m%d'), self.date_to.strftime('%Y%m%d'))

    def build_xlsx(self):
        self.ensure_one()
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {'in_memory': True})
        styles = {
            'title': book.add_format({'bold': True, 'font_size': 16, 'font_color': BRAND}),
            'subtitle': book.add_format({'italic': True, 'font_color': '#6B7280'}),
            'head': book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': BRAND, 'border': 1,
                                     'border_color': '#D1D5DB', 'valign': 'vcenter', 'text_wrap': True}),
            'cell': book.add_format({'border': 1, 'border_color': '#E5E7EB'}),
            'zebra': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'bg_color': '#F7F5FF'}),
            'date': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'num_format': 'dd/mm/yyyy'}),
            'time': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'num_format': 'hh:mm:ss'}),
            'hours': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'num_format': '[h]:mm'}),
            'int': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'num_format': '0'}),
            'kpi': book.add_format({'bold': True, 'font_size': 14, 'font_color': BRAND, 'align': 'center',
                                    'bg_color': '#F5F3FF', 'border': 1, 'border_color': '#DDD6FE'}),
            'kpi_label': book.add_format({'font_color': '#6B7280', 'align': 'center', 'font_size': 9,
                                          'bg_color': '#F5F3FF', 'border': 1, 'border_color': '#DDD6FE'}),
            'bad': book.add_format({'border': 1, 'border_color': '#E5E7EB', 'font_color': '#B91C1C', 'bold': True}),
        }
        getattr(self, '_xlsx_%s' % self.report_type)(book, styles)
        book.close()
        return buffer.getvalue()

    def _sheet(self, book, styles, name, title, headers, widths, kpis=None):
        sheet = book.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.write(0, 0, title, styles['title'])
        sheet.write(1, 0, '%s — %s · %s%s' % (
            self.env.company.name, _('Période du %s', self.period_label()),
            _('édité le %s', fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')),
            (' · ' + self.filters_label()) if self.filters_label() else ''), styles['subtitle'])
        row = 3
        if kpis:
            for column, (value, label) in enumerate(kpis):
                sheet.write(row, column, value, styles['kpi'])
                sheet.write(row + 1, column, label, styles['kpi_label'])
            row += 3
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(row, column, header, styles['head'])
            sheet.set_column(column, column, width)
        sheet.set_row(row, 28)
        sheet.freeze_panes(row + 1, 0)
        return sheet, row

    def _write_rows(self, sheet, styles, header_row, rows, formats):
        for index, values in enumerate(rows):
            zebra = index % 2
            for column, value in enumerate(values):
                fmt = formats[column] if formats and formats[column] else ('zebra' if zebra else 'cell')
                if value is None or value is False:
                    sheet.write_blank(header_row + 1 + index, column, None, styles['zebra' if zebra else 'cell'])
                elif fmt == 'date':
                    sheet.write_datetime(header_row + 1 + index, column, datetime.combine(value, time.min), styles['date'])
                else:
                    sheet.write(header_row + 1 + index, column, value, styles[fmt])
        if rows:
            sheet.autofilter(header_row, 0, header_row + len(rows), len(rows[0]) - 1)

    def _xlsx_attendance(self, book, styles):
        data = self._attendance_data()
        totals = data['totals']
        headers = ['Employé', 'Département', 'Jours prévus', 'Présent', 'Absences', 'Absences non just.',
                   'Congés / fériés', 'Retards', 'Retard (h)', 'Départs anticipés (h)', 'Heures sup. (h)',
                   'Pointages incomplets', 'Heures travaillées', 'Heures prévues']
        sheet, header_row = self._sheet(book, styles, 'Synthèse', 'Rapport de présence', headers,
                                        [28, 20, 11, 9, 10, 12, 12, 9, 10, 12, 11, 12, 13, 12], kpis=[
                                            (len(data['employees']), 'employés'),
                                            (totals['present_days'], 'jours de présence'),
                                            (totals['absent_days'], 'absences'),
                                            (totals['late_count'], 'retards'),
                                            (round(totals['worked_hours'], 1), 'heures travaillées')])
        rows = [[line['employee'].name, line['employee'].department_id.name or '', line['planned_days'],
                 line['present_days'], line['absent_days'], line['unjustified_absences'], line['leave_days'],
                 line['late_count'], line['late_minutes'] / 1440.0, line['early_minutes'] / 1440.0,
                 line['overtime_minutes'] / 1440.0, line['incomplete_days'], line['worked_hours'] / 24.0,
                 line['planned_hours'] / 24.0] for line in data['employees']]
        self._write_rows(sheet, styles, header_row, rows,
                         [None, None, 'int', 'int', 'int', 'int', 'int', 'int', 'hours', 'hours', 'hours', 'int',
                          'hours', 'hours'])
        status = dict(self.env['biometric.attendance.day']._fields['status'].selection)
        detail_headers = ['Date', 'Jour', 'Employé', 'Département', 'Prévu (début)', 'Prévu (fin)', 'Arrivée',
                          'Départ', 'Travaillé', 'Retard (min)', 'Départ anticipé (min)', 'Heures sup. (min)',
                          'Statut', 'Justifié', 'Observations', 'Justification']
        sheet, header_row = self._sheet(book, styles, 'Détail', 'Détail jour par jour', detail_headers,
                                        [11, 6, 26, 18, 10, 10, 9, 9, 10, 10, 12, 11, 18, 8, 40, 30])
        rows = []
        for line in data['employees']:
            for day in line['days']:
                rows.append([day.date, DAY_NAMES[day.date.weekday()], line['employee'].name,
                             day.department_id.name or '',
                             float_to_hhmm(day.planned_start) if day.plan_source != 'none' else '',
                             float_to_hhmm(day.planned_end) if day.plan_source != 'none' else '',
                             float_to_hhmm(day.arrival_time) if day.arrival else '',
                             float_to_hhmm(day.departure_time) if day.departure else '',
                             day.worked_hours / 24.0, day.late_minutes, day.early_leave_minutes,
                             day.overtime_minutes, status.get(day.status, ''), 'Oui' if day.justified else '',
                             day.anomaly or '', day.justification_note or ''])
        self._write_rows(sheet, styles, header_row, rows,
                         ['date', None, None, None, None, None, None, None, 'hours', 'int', 'int', 'int', None,
                          None, None, None])

    def _xlsx_punches(self, book, styles):
        data = self._punches_data()
        stats = data['stats']
        headers = ['Date', 'Jour', 'Heure', 'Employé', 'Département', 'Identifiant', 'Pointeuse', 'Méthode',
                   'Rôle dans la journée', 'Origine', 'Motif']
        sheet, header_row = self._sheet(book, styles, 'Pointages', 'Pointages', headers,
                                        [11, 6, 10, 26, 18, 11, 20, 12, 18, 14, 30], kpis=[
                                            (stats['total'], 'pointages'), (stats['employees'], 'employés'),
                                            (stats['days'], 'jours'), (stats['manual'], 'saisies manuelles')])
        rows = [[row['date'], DAY_NAMES[row['date'].weekday()], row['time'], row['employee'], row['department'],
                 row['user_id'], row['device'], row['method'], row['role'], row['source'], row['note']]
                for row in data['rows']]
        self._write_rows(sheet, styles, header_row, rows, ['date'] + [None] * 10)

    def _xlsx_users(self, book, styles):
        data = self._users_data()
        stats = data['stats']
        headers = ['Pointeuse', 'Identifiant', 'Nom sur la pointeuse', 'Employé Odoo', 'Département', 'Rôle',
                   'Carte', 'État', 'Dernière synchronisation', 'Détails', 'Actif']
        sheet, header_row = self._sheet(book, styles, 'Utilisateurs', 'Utilisateurs des pointeuses', headers,
                                        [20, 11, 24, 26, 18, 14, 12, 14, 18, 45, 7], kpis=[
                                            (stats['total'], 'utilisateurs'), (stats['mapped'], 'associés'),
                                            (stats['unmapped'], 'sans employé'), (stats['errors'], 'en erreur')])
        rows = [[row['device'], row['user_id'], row['device_name'], row['employee'] or 'Non associé',
                 row['department'], row['privilege'], row['card'], row['state'], row['last_sync'], row['message'],
                 'Oui' if row['active'] else 'Non'] for row in data['rows']]
        self._write_rows(sheet, styles, header_row, rows, None)

    def _xlsx_devices(self, book, styles):
        data = self._devices_data()
        headers = ['Pointeuse', 'Modèle', 'N° de série', 'Firmware', 'Adresse', 'Mode', 'État', 'Dernière synchro',
                   'Mémoire', 'Pointages (période)', 'Employés', 'Opérations journalisées', 'Erreurs', 'Avertissements']
        sheet, header_row = self._sheet(book, styles, 'Pointeuses', 'Activité des pointeuses', headers,
                                        [20, 12, 16, 20, 18, 22, 18, 16, 14, 12, 10, 12, 9, 12])
        rows = [[item['device'].name, item['device'].info_device_name or '', item['device'].info_serial or '',
                 item['device'].info_firmware or '', '%s:%s' % (item['device'].device_ip, item['device'].port_number),
                 item['mode'], item['sync_state'], item['last_sync'], item['memory'], item['punches'],
                 item['employees'], item['logs_total'], item['logs_errors'], item['logs_warnings']]
                for item in data['devices']]
        self._write_rows(sheet, styles, header_row, rows,
                         [None] * 9 + ['int', 'int', 'int', 'int', 'int'])
        sheet, header_row = self._sheet(book, styles, 'Pointages par jour', 'Pointages par jour et par pointeuse',
                                        ['Date', 'Jour'] + [item['device'].name for item in data['devices']],
                                        [11, 6] + [16] * len(data['devices']))
        rows = []
        for index, current in enumerate(data['devices'][0]['days'] if data['devices'] else []):
            rows.append([current['date'], DAY_NAMES[current['date'].weekday()]]
                        + [item['days'][index]['count'] for item in data['devices']])
        self._write_rows(sheet, styles, header_row, rows, ['date', None] + ['int'] * len(data['devices']))
        sheet, header_row = self._sheet(book, styles, 'Erreurs', 'Dernières erreurs des pointeuses',
                                        ['Pointeuse', 'Date', 'Opération', 'Message'], [20, 16, 24, 90])
        rows = [[item['device'].name, error['date'], error['operation'], error['message']]
                for item in data['devices'] for error in item['last_errors']]
        self._write_rows(sheet, styles, header_row, rows, None)
