# -*- coding: utf-8 -*-
"""Excel export of the attendance reports."""
from odoo import http
from odoo.http import request


class BiometricReportXlsxController(http.Controller):

    @http.route('/primetech_biometric/report/xlsx/<int:wizard_id>', type='http', auth='user')
    def report_xlsx(self, wizard_id, **kwargs):
        if not request.env.user.has_group('hr_attendance.group_hr_attendance_manager'):
            return request.not_found()
        wizard = request.env['biometric.attendance.report.wizard'].browse(wizard_id).exists()
        if not wizard or wizard.create_uid != request.env.user:
            return request.not_found()
        return request.make_response(wizard.build_xlsx(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', http.content_disposition(wizard.xlsx_filename())),
        ])
