#-*- coding:utf-8 -*-
from odoo import api, models, _
from datetime import date, datetime

CAT = {
    '01' : 'I',
    '02' : 'II',
    '03' : 'III',
    '04' : 'IV',
    '05' : 'V',
    '06' : 'VI',
    '07' : 'VII',
    '08' : 'VIII',
    '09' : 'IX',
    '10' : 'X',
    '11' : 'XI',
    '12' : 'XII'
}

MARITAL = {
    False : ' ',
    'single' : _('Single'),
    'married' : _('Married'),
    'widower' : _('Widower'),
    'divorced' : _('Divorced')
}

class PayslipReport(models.AbstractModel):
    _name = 'report.primetech_rh.report_payslip'

    def _get_cumul(self, input_code, period_end, employee_id):
        payslip_obj = self.env['hr.payslip']
        current_year = str(period_end.year) + "-01-01"
        payslips = payslip_obj.search([('employee_id', '=', employee_id.id), ('date_from', '>=', current_year), ('date_to', '<=', period_end), ('state', '!=', 'cancel')])
        cumul = 0
        for payslip in payslips:
            line = payslip.line_ids.filtered(lambda line: line.code == input_code)
            cumul += len(line) > 0 and line[0].total or 0
        
        return cumul

    def _get_cumul_indem_remb(self, o, period_end, employee_id):
        payslip_obj = self.env['hr.payslip']
        current_year = str(period_end.year) + "-01-01"
        payslips = payslip_obj.search([('employee_id', '=', employee_id.id), ('date_from', '>=', current_year), ('date_to', '<=', period_end), ('state', '!=', 'cancel')])
        cumul = 0
        for payslip in payslips:
            cumul += sum([l.total for l in payslip.line_ids.filtered(lambda line: not line.salary_rule_id.compute_leave and line.appears_on_payslip)])
        
        return cumul

    def _get_summary_leave(self, employee_id, date_to, date_from):
        contract = self.env['hr.contract'].search([('employee_id', '=', employee_id.id)], order='date_start asc', limit=1)
        date_start = contract.date_start and contract.date_start or False
        date_end = date_to

        def diff_month(d1, d2):
            return (d1.year - d2.year) * 12 + d1.month - d2.month + 1

        months = diff_month(date_end, date_start)
        if months > 0:
            nb_years = int(months/12)
            nb_month = months%12
            seniority = str(nb_years) + (nb_years not in (0,1) and _(" years ") or _(" year ")) + str(nb_month) + (nb_month not in (0,1) and _(" months") or _(" month"))
        else:
            seniority = _("0 year 0 month")

        nb_month = months % 12

        acquired = nb_month * 1.5
        taken = 0

        return {
            'seniority' : seniority,
            'acquired' : acquired,
            'taken' : taken,
            'remain' : acquired - taken
        }



    def _get_hiring_date(self, employee):
        contract_obj = self.env['hr.contract']
        contract = contract_obj.search([('employee_id', '=', employee.id)], order='date_start asc', limit=1)
        return contract.date_start

    @api.model
    def _get_report_values(self, docids, data=None):
        payslips = self.env['hr.payslip'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip',
            'docs': payslips,
            'data': data,
            'cat': CAT,
            'marital': MARITAL,
            'hiring_date': self._get_hiring_date,
            'cumul': self._get_cumul,
            'indm_remb': self._get_cumul_indem_remb,
            'leaves': self._get_summary_leave,
        }
        # return self.env['report'].render('primetech_rh.report_payslip', docargs)
