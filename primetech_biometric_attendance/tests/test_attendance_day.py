# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# 2026-11-02 is a Monday; Africa/Douala is UTC+1 (no daylight saving time).
MONDAY = date(2026, 11, 2)
SATURDAY = date(2026, 11, 7)


def utc(day, hour, minute=0):
    """Local Douala time -> naive UTC datetime."""
    return datetime(day.year, day.month, day.day, hour - 1, minute)


@tagged('post_install', '-at_install')
class TestAttendanceDay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'biometric_punch_mode': 'first_last',
            'biometric_min_punch_interval': 2,
            'biometric_generate_attendance': True,
        })
        cls.schedule = cls.env['biometric.attendance.schedule'].create({
            'name': 'Bureau',
            'timezone': 'Africa/Douala',
            'grace_minutes': 10,
            'late_count_mode': 'from_start',
            'early_leave_tolerance': 5,
            'overtime_threshold': 15,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Agent Pointage',
            'device_id_num': '501',
            'biometric_schedule_id': cls.schedule.id,
        })
        cls.Day = cls.env['biometric.attendance.day']

    def punch(self, moment, employee=None):
        return self.env['zk.machine.attendance'].create({
            'employee_id': (employee or self.employee).id,
            'punching_time': moment,
            'source': 'device',
            'punch_type': '255',
        })

    def day(self, day=MONDAY, employee=None):
        return self.Day.search([('employee_id', '=', (employee or self.employee).id),
                                ('date', '=', day)])

    def test_default_schedule_lines(self):
        self.assertEqual(sorted(self.schedule.line_ids.mapped('day_of_week')), ['0', '1', '2', '3', '4'])
        self.assertAlmostEqual(self.schedule.weekly_hours, 40.0)
        self.assertEqual(self.employee._get_biometric_schedule(), self.schedule)

    def test_schedule_resolution_department_then_company(self):
        other = self.schedule.copy({'name': 'Atelier'})
        default = self.schedule.copy({'name': 'Défaut'})
        department = self.env['hr.department'].create({'name': 'Atelier', 'biometric_schedule_id': other.id})
        employee = self.env['hr.employee'].create({'name': 'Ouvrier', 'department_id': department.id})
        self.assertEqual(employee._get_biometric_schedule(), other)
        department.biometric_schedule_id = False
        self.company.biometric_default_schedule_id = default
        self.assertEqual(employee._get_biometric_schedule(), default)

    def test_on_time_day(self):
        self.punch(utc(MONDAY, 8, 5))
        self.punch(utc(MONDAY, 17, 0))
        day = self.day()
        self.assertEqual(day.status, 'present')
        self.assertEqual(day.late_minutes, 0)
        self.assertAlmostEqual(day.worked_hours, 7.9167, places=3)  # minus 1 h lunch break
        self.assertEqual(day.hr_attendance_ids.check_in, utc(MONDAY, 8, 5))
        self.assertEqual(day.hr_attendance_ids.check_out, utc(MONDAY, 17, 0))
        self.assertEqual(day.hr_attendance_ids.in_mode, 'biometric')

    def test_late_arrival_counted_from_planned_start(self):
        self.punch(utc(MONDAY, 8, 25))
        self.punch(utc(MONDAY, 17, 0))
        day = self.day()
        self.assertEqual(day.status, 'late')
        self.assertTrue(day.is_late)
        self.assertEqual(day.late_minutes, 25)

    def test_late_arrival_counted_after_grace(self):
        self.schedule.late_count_mode = 'after_grace'
        self.punch(utc(MONDAY, 8, 25))
        self.punch(utc(MONDAY, 17, 0))
        self.assertEqual(self.day().late_minutes, 15)

    def test_early_leave_and_overtime(self):
        self.punch(utc(MONDAY, 8, 0))
        self.punch(utc(MONDAY, 16, 30))
        self.assertEqual(self.day().early_leave_minutes, 30)
        self.punch(utc(MONDAY, 18, 0))
        day = self.day()
        self.assertEqual(day.early_leave_minutes, 0)
        self.assertEqual(day.overtime_minutes, 60)

    def test_duplicates_are_ignored(self):
        first = self.punch(utc(MONDAY, 8, 0))
        duplicate = self.punch(datetime(2026, 11, 2, 7, 1))
        self.punch(utc(MONDAY, 17, 0))
        day = self.day()
        self.assertEqual(day.punch_count, 2)
        self.assertEqual(first.punch_role, 'in')
        self.assertEqual(duplicate.punch_role, 'duplicate')

    def test_single_past_punch_is_incomplete(self):
        self.punch(utc(MONDAY, 8, 0))
        day = self.day()
        self.assertEqual(day.status, 'incomplete')
        self.assertTrue(day.missing_check_out)
        self.assertFalse(day.hr_attendance_ids, 'An open attendance must not be created for a past day')

    def test_single_punch_in_check_out_window(self):
        self.schedule.enforce_windows = True
        self.punch(utc(MONDAY, 17, 5))
        day = self.day()
        self.assertTrue(day.missing_check_in)
        self.assertFalse(day.arrival)
        self.assertEqual(day.departure, utc(MONDAY, 17, 5))

    def test_outside_window(self):
        self.schedule.enforce_windows = True
        self.punch(utc(MONDAY, 5, 0))
        self.punch(utc(MONDAY, 17, 0))
        self.assertTrue(self.day().outside_window)

    def test_absence_and_justification_are_kept(self):
        self.punch(utc(MONDAY, 8, 0))
        self.punch(utc(MONDAY, 17, 0))
        tuesday = date(2026, 11, 3)
        self.Day._recompute_period(tuesday, tuesday, self.employee)
        absence = self.day(tuesday)
        self.assertEqual(absence.status, 'absent')
        absence.write({'justified': True, 'justification_note': 'Maladie'})
        self.Day._recompute_period(tuesday, tuesday, self.employee)
        self.assertTrue(absence.justified)
        self.assertEqual(absence.justified_by, self.env.user)

    def test_no_absence_before_first_punch(self):
        self.punch(utc(MONDAY, 8, 0))
        previous_friday = date(2026, 10, 30)
        self.Day._recompute_period(previous_friday, previous_friday, self.employee)
        self.assertFalse(self.day(previous_friday))

    def test_rest_day_punches_are_extra_work(self):
        self.punch(utc(SATURDAY, 9, 0))
        self.punch(utc(SATURDAY, 12, 0))
        day = self.day(SATURDAY)
        self.assertEqual(day.status, 'extra')
        self.assertEqual(day.overtime_minutes, 180)

    def test_public_holiday(self):
        self.punch(utc(MONDAY, 8, 0))
        holiday_day = date(2026, 11, 4)
        self.env['resource.calendar.leaves'].create({
            'name': 'Jour férié',
            'date_from': datetime(2026, 11, 3, 23, 0),
            'date_to': datetime(2026, 11, 4, 22, 59),
            'company_id': self.company.id,
            'time_type': 'leave',
        })
        self.Day._recompute_period(holiday_day, holiday_day, self.employee)
        self.assertEqual(self.day(holiday_day).status, 'holiday')

    def test_pairs_mode(self):
        self.company.biometric_punch_mode = 'pairs'
        self.punch(utc(MONDAY, 8, 0))
        self.punch(utc(MONDAY, 12, 0))
        self.punch(utc(MONDAY, 13, 0))
        self.punch(utc(MONDAY, 17, 0))
        day = self.day()
        self.assertAlmostEqual(day.worked_hours, 8.0)
        self.assertEqual(len(day.hr_attendance_ids), 2)

    def test_manual_punch_completes_the_day(self):
        self.punch(utc(MONDAY, 8, 0))
        self.assertEqual(self.day().status, 'incomplete')
        self.env['zk.machine.attendance'].create({
            'employee_id': self.employee.id,
            'punching_time': utc(MONDAY, 17, 0),
            'source': 'manual',
            'note': 'Oubli',
        })
        self.assertEqual(self.day().status, 'present')

    def test_resource_calendar_fallback(self):
        employee = self.env['hr.employee'].create({'name': 'Sans horaire', 'device_id_num': '777'})
        self.company.biometric_default_schedule_id = False
        tz, plan = employee._get_biometric_day_plan(MONDAY)
        self.assertTrue(plan)
        self.assertEqual(plan['source'], 'calendar')
        self.assertFalse(employee._get_biometric_day_plan(SATURDAY)[1])

    def test_dashboard_data(self):
        self.punch(utc(MONDAY, 8, 30))
        self.punch(utc(MONDAY, 17, 0))
        data = self.Day.get_dashboard_data('2026-11-02')
        self.assertEqual(data['kpis']['late'], 1)
        self.assertEqual(data['late'][0]['late_minutes'], 30)
        self.assertEqual(len(data['trend']), 14)
