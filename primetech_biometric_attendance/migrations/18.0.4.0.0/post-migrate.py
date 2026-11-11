# -*- coding: utf-8 -*-
"""Clean the punches imported with a wrong timezone and build the attendance days."""
import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # 1. Link the legacy punches to their device.
    devices = env['biometric.device.details'].with_context(active_test=False).search([])
    if len(devices) == 1:
        cr.execute("UPDATE zk_machine_attendance SET device_id = %s WHERE device_id IS NULL",
                   [devices.id])
    else:
        for device in devices.filtered('address_id'):
            cr.execute("""UPDATE zk_machine_attendance SET device_id = %s
                           WHERE device_id IS NULL AND address_id = %s""",
                       [device.id, device.address_id.id])

    # 2. Before 18.0.4 the scheduled synchronisation converted the device time
    #    with the timezone of OdooBot (empty, hence GMT): those punches were
    #    stored one hour in the future and duplicated the punches imported by a
    #    manual synchronisation.  A punch cannot be later than its import date.
    cr.execute("""
        SELECT id, employee_id, punching_time FROM zk_machine_attendance
         WHERE source = 'device' AND punching_time > create_date + interval '5 minutes'
    """)
    shifted = cr.fetchall()
    if shifted:
        for _id, employee_id, punching_time in shifted:
            cr.execute("""DELETE FROM hr_attendance
                           WHERE employee_id = %s AND check_in = %s
                             AND check_in > create_date + interval '5 minutes'""",
                       [employee_id, punching_time])
        cr.execute("DELETE FROM zk_machine_attendance WHERE id IN %s",
                   [tuple(row[0] for row in shifted)])
        _logger.warning('primetech_biometric_attendance: %s punch(es) stored with a wrong '
                        'timezone have been removed', len(shifted))

    # 3. Build the attendance days from the first punch.
    cr.execute("SELECT min(punching_time) FROM zk_machine_attendance")
    first = cr.fetchone()[0]
    if first:
        today = fields.Date.context_today(env['biometric.attendance.day'])
        count = env['biometric.attendance.day']._recompute_period(first.date(), today)
        _logger.info('primetech_biometric_attendance: %s attendance day(s) analysed', count)
