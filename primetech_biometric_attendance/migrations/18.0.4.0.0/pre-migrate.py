# -*- coding: utf-8 -*-
"""Prepare the punches table before zk.machine.attendance stops inheriting hr.attendance."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP VIEW IF EXISTS daily_attendance")
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'zk_machine_attendance'")
    if not cr.fetchone():
        return
    # check_in was required through hr.attendance; the column is dropped with the field.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'zk_machine_attendance' AND column_name = 'check_in'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE zk_machine_attendance ALTER COLUMN check_in DROP NOT NULL")
    # Every punch stored so far was read from a device: do not let the ORM
    # fill the new required field with its default value ('manual').
    cr.execute("ALTER TABLE zk_machine_attendance ADD COLUMN IF NOT EXISTS source varchar")
    cr.execute("UPDATE zk_machine_attendance SET source = 'device' WHERE source IS NULL")
    _logger.info('primetech_biometric_attendance: %s punch(es) marked as read from a device', cr.rowcount)
