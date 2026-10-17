# -*- encoding:utf-8 -*-

from odoo import api, fields, models, _
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, AccessError, ValidationError
import re, string, random
from odoo import SUPERUSER_ID
import logging
LOGGER = logging.getLogger(__name__)

@api.model
def _lang_get(self):
    return self.env['res.lang'].get_installed()


class hr_employee_child(models.Model):

    _name       = "hr.employee.child"


    name = fields.Char('Name')
    nb_certif = fields.Char('Birth certificate number')
    birth_date = fields.Date('Birth Date')

    _sql_constraints = [
        ('nb_certif_uniq', 'unique(nb_certif)', 'The Birth certificate number must be unique!'),
    ]


class hr_employee_contact(models.Model):

    _name       = "hr.employee.contact"

    name = fields.Char('Name')
    phone = fields.Char('Phone number')
    link = fields.Char('Link')


class hr_employee(models.Model):

    _name       = "hr.employee"
    _order      = 'matricule'
    _inherit    = ['hr.employee']

    category_id = fields.Many2one('hr.employee.category', string='Category', tracking=True)
    echelon_id = fields.Many2one('hr.paie.echelon', string='Echelon', tracking=True)
    matricule = fields.Char('Matricule')
    children = fields.Integer(string='Number of children', compute='_get_nb_children')
    contact_ids = fields.Many2many('hr.employee.contact', string='Contacts')
    childs_ids = fields.Many2many('hr.employee.child')
    seniority = fields.Char(compute='_get_seniority', string='Seniority')
    show_category = fields.Boolean('Able to see Category and Echelon', compute='_compute_show_category', default=True)
    lang = fields.Selection(_lang_get, string='Language', default=lambda self: self.env.lang,
                            help="If the selected language is loaded in the system, all documents related to "
                                 "this contact will be printed in this language. If not, it will be English.")
    length_of_service = fields.Integer(compute='_get_seniority', string='Length of service (Months)')
    cnps = fields.Char('CNPS Number')
    except_cat = fields.Boolean('Except category')
    last_leave_date = fields.Date('Last leave date', store=True)
    hired_date = fields.Date(compute='_get_hiring_date', string='Hiring date')
    age = fields.Integer('Age', compute='_get_age')
    birthday = fields.Date('Date of Birth', groups="base.group_user")
    ending_date = fields.Date(compute='_get_ending_date', string='Ending date')

    _sql_constraints = [
        ('matricule_uniq', 'unique(matricule)', 'The matricule must be unique!'),
    ]

    @api.model
    def get_rh_dashboard_data(self, options=None):
        """Indicateurs RH utilisés par le tableau de bord interactif."""
        options = options or {}
        today = fields.Date.context_today(self)
        period = options.get('period') or 'month'
        if period == 'today':
            date_from = date_to = today
        elif period == 'week':
            date_from, date_to = today - timedelta(days=today.weekday()), today
        elif period == 'quarter':
            first_month = ((today.month - 1) // 3) * 3 + 1
            date_from = today.replace(month=first_month, day=1)
            date_to = today
        elif period == 'semester':
            date_from = today.replace(month=1 if today.month <= 6 else 7, day=1)
            date_to = today
        elif period == 'year':
            date_from, date_to = today.replace(month=1, day=1), today
        elif period == 'custom':
            date_from = fields.Date.to_date(options.get('date_from')) or today.replace(day=1)
            date_to = fields.Date.to_date(options.get('date_to')) or today
        else:
            date_from, date_to = today.replace(day=1), today

        def _range_for(value):
            if value == 'today':
                return today, today
            if value == 'week':
                return today - timedelta(days=today.weekday()), today
            if value == 'year':
                return today.replace(month=1, day=1), today
            return today.replace(day=1), today

        attendance_from, attendance_to = _range_for(options.get('attendance_period') or period)
        leave_from, leave_to = _range_for(options.get('leave_period') or period)
        workforce_from, workforce_to = _range_for(options.get('workforce_period') or period)
        payroll_from, payroll_to = _range_for(options.get('payroll_period') or period)

        company_ids = self.env.companies.ids
        department_id = int(options.get('department_id') or 0)
        employee_domain = [('active', '=', True), ('company_id', 'in', company_ids)]
        if department_id:
            employee_domain.append(('department_id', '=', department_id))
        Contract = self.env['hr.contract']
        Payslip = self.env['hr.payslip']
        Leave = self.env['hr.leave']
        Attendance = self.env['hr.attendance']
        contract_domain = [
            ('company_id', 'in', company_ids), ('state', '=', 'open'),
            ('date_start', '<=', date_to), '|', ('date_end', '=', False), ('date_end', '>=', date_from),
        ]
        if department_id:
            contract_domain.append(('employee_id.department_id', '=', department_id))
        payslip_domain = [
            ('company_id', 'in', company_ids), ('state', 'in', ('done', 'paid')),
            ('date_to', '>=', date_from), ('date_to', '<=', date_to),
        ]
        leave_domain = [
            ('company_id', 'in', company_ids), ('state', 'in', ('validate', 'validate1')),
            ('date_from', '<=', date_to), ('date_to', '>=', date_from),
        ]
        leave_pending_domain = [
            ('company_id', 'in', company_ids), ('state', 'in', ('confirm', 'validate1')),
            ('request_date_from', '<=', date_to), ('request_date_to', '>=', date_from),
        ]
        leave_today_domain = [
            ('company_id', 'in', company_ids), ('state', '=', 'validate'),
            ('date_from', '<=', today), ('date_to', '>=', today),
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))
            leave_domain.append(('employee_id.department_id', '=', department_id))
            leave_pending_domain.append(('employee_id.department_id', '=', department_id))
            leave_today_domain.append(('employee_id.department_id', '=', department_id))

        attendance_domain = [
            ('employee_id.company_id', 'in', company_ids),
            ('check_in', '>=', fields.Datetime.to_string(datetime.combine(date_from, datetime.min.time()))),
            ('check_in', '<', fields.Datetime.to_string(datetime.combine(date_to + timedelta(days=1), datetime.min.time()))),
        ]
        attendance_open_domain = [('employee_id.company_id', 'in', company_ids), ('check_out', '=', False)]
        if department_id:
            attendance_domain.append(('department_id', '=', department_id))
            attendance_open_domain.append(('department_id', '=', department_id))

        attendance_today_domain = [
            ('employee_id.company_id', 'in', company_ids),
            ('check_in', '>=', fields.Datetime.to_string(datetime.combine(today, datetime.min.time()))),
            ('check_in', '<', fields.Datetime.to_string(datetime.combine(today + timedelta(days=1), datetime.min.time()))),
        ]
        if department_id:
            attendance_today_domain.append(('department_id', '=', department_id))

        attendance_panel_domain = [
            ('employee_id.company_id', 'in', company_ids),
            ('check_in', '>=', fields.Datetime.to_string(datetime.combine(attendance_from, datetime.min.time()))),
            ('check_in', '<', fields.Datetime.to_string(datetime.combine(attendance_to + timedelta(days=1), datetime.min.time()))),
        ]
        leave_panel_domain = [
            ('company_id', 'in', company_ids), ('state', '=', 'validate'),
            ('date_from', '<=', leave_to), ('date_to', '>=', leave_from),
        ]
        payroll_panel_domain = [
            ('company_id', 'in', company_ids), ('state', '=', 'done'),
            ('date_to', '>=', payroll_from), ('date_to', '<=', payroll_to),
        ]
        if department_id:
            attendance_panel_domain.append(('department_id', '=', department_id))
            leave_panel_domain.append(('employee_id.department_id', '=', department_id))
            payroll_panel_domain.append(('employee_id.department_id', '=', department_id))

        def _net_amount(slips):
            total = 0.0
            for slip in slips:
                net_line = slip.line_ids.filtered(lambda line: line.code in ('NET', 'NETWAGE', 'NET_A_PAYER'))[:1]
                total += net_line.total if net_line else 0.0
            return total

        def _gross_amount(slips):
            total = 0.0
            for slip in slips:
                gross_line = slip.line_ids.filtered(lambda line: line.code in ('BRUT', 'GROSS', 'GROSSWAGE'))[:1]
                total += gross_line.total if gross_line else 0.0
            return total

        slips = Payslip.search(payslip_domain)
        validated_leaves = Leave.search(leave_domain)
        attendances = Attendance.search(attendance_domain)
        attendance_today = Attendance.search(attendance_today_domain)
        attendance_panel = Attendance.search(attendance_panel_domain)
        leave_panel = Leave.search(leave_panel_domain)
        payroll_panel = Payslip.search(payroll_panel_domain)
        departments = self.env['hr.department'].search([('company_id', 'in', company_ids)], order='name')
        distribution = []
        employees = self.search(employee_domain)
        for department in departments:
            count = len(employees.filtered(lambda employee: employee.department_id == department))
            if count:
                distribution.append({'id': department.id, 'name': department.name, 'count': count})
        without_department = len(employees.filtered(lambda employee: not employee.department_id))
        if without_department:
            distribution.append({'id': False, 'name': _('Sans service'), 'count': without_department})

        leave_distribution = []
        for leave_type in leave_panel.mapped('holiday_status_id'):
            type_leaves = leave_panel.filtered(lambda leave: leave.holiday_status_id == leave_type)
            leave_distribution.append({
                'id': leave_type.id,
                'name': leave_type.name,
                'days': round(sum(type_leaves.mapped('number_of_days')), 1),
                'count': len(type_leaves),
            })

        chart = []
        cursor = date_from
        while cursor <= date_to:
            if period == 'year':
                next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
                end = min(date_to, next_month - timedelta(days=1))
                label = ('Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc')[cursor.month - 1]
            elif period in ('quarter', 'semester', 'custom'):
                end = min(date_to, cursor + timedelta(days=6))
                label = '%s-%s' % (cursor.strftime('%d/%m'), end.strftime('%d/%m'))
            else:
                end = cursor
                label = cursor.strftime('%d/%m')
            bucket_contracts = Contract.search(contract_domain + [('date_start', '>=', cursor), ('date_start', '<=', end)])
            bucket_slips = Payslip.search(payslip_domain + [('date_to', '>=', cursor), ('date_to', '<=', end)])
            chart.append({
                'label': label,
                'date_from': fields.Date.to_string(cursor),
                'date_to': fields.Date.to_string(end),
                'recruitments': len(bucket_contracts),
                'payroll': _net_amount(bucket_slips),
            })
            cursor = end + timedelta(days=1)

        def _buckets(start, end, yearly=False):
            cursor = start
            result = []
            while cursor <= end:
                if yearly:
                    next_date = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
                    bucket_end = min(end, next_date - timedelta(days=1))
                    label = ('Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc')[cursor.month - 1]
                elif (end - start).days > 31:
                    bucket_end = min(end, cursor + timedelta(days=6))
                    label = '%s-%s' % (cursor.strftime('%d/%m'), bucket_end.strftime('%d/%m'))
                else:
                    bucket_end = cursor
                    label = cursor.strftime('%d/%m')
                result.append((cursor, bucket_end, label))
                cursor = bucket_end + timedelta(days=1)
            return result

        workforce_chart = []
        for start, end, label in _buckets(workforce_from, workforce_to, (options.get('workforce_period') or period) == 'year'):
            workforce_domain = [('company_id', 'in', company_ids), ('date_start', '<=', end), '|', ('date_end', '=', False), ('date_end', '>=', end)]
            arrivals_domain = [('company_id', 'in', company_ids), ('date_start', '>=', start), ('date_start', '<=', end)]
            departures_domain = [('company_id', 'in', company_ids), ('date_end', '>=', start), ('date_end', '<=', end)]
            if department_id:
                workforce_domain.append(('employee_id.department_id', '=', department_id))
                arrivals_domain.append(('employee_id.department_id', '=', department_id))
                departures_domain.append(('employee_id.department_id', '=', department_id))
            workforce_chart.append({'label': label, 'date_from': fields.Date.to_string(start), 'date_to': fields.Date.to_string(end), 'total': len(Contract.search(workforce_domain).mapped('employee_id')), 'arrivals': len(Contract.search(arrivals_domain).mapped('employee_id')), 'departures': len(Contract.search(departures_domain).mapped('employee_id'))})

        payroll_chart = []
        for start, end, label in _buckets(payroll_from, payroll_to, (options.get('payroll_period') or period) == 'year'):
            bucket_domain = [('company_id', 'in', company_ids), ('state', '=', 'done'), ('date_to', '>=', start), ('date_to', '<=', end)]
            if department_id:
                bucket_domain.append(('employee_id.department_id', '=', department_id))
            bucket_slips = Payslip.search(bucket_domain)
            payroll_chart.append({'label': label, 'date_from': fields.Date.to_string(start), 'date_to': fields.Date.to_string(end), 'net': _net_amount(bucket_slips), 'gross': _gross_amount(bucket_slips), 'count': len(bucket_slips)})

        recent = []
        for slip in Payslip.search(payslip_domain, order='date_to desc, id desc', limit=8):
            recent.append({
                'id': slip.id,
                'name': slip.name or slip.number or _('Bulletin sans référence'),
                'employee': slip.employee_id.name,
                'department': slip.employee_id.department_id.name or _('Sans service'),
                'date': fields.Date.to_string(slip.date_to),
                'amount': _net_amount(slip),
            })

        recent_attendance = [{
            'id': attendance.id,
            'employee': attendance.employee_id.name,
            'check_in': fields.Datetime.context_timestamp(self, attendance.check_in).strftime('%H:%M') if attendance.check_in else '-',
            'status': _('Présent') if not attendance.check_out else _('Terminé'),
            'open': not attendance.check_out,
        } for attendance in attendance_panel.sorted(key=lambda item: item.check_in, reverse=True)[:5]]
        recent_leaves = [{
            'id': leave.id,
            'employee': leave.employee_id.name,
            'type': leave.holiday_status_id.name,
            'period': '%s - %s' % (fields.Date.to_string(leave.request_date_from), fields.Date.to_string(leave.request_date_to)),
            'state': dict(leave._fields['state'].selection).get(leave.state, leave.state),
        } for leave in leave_panel.sorted(key=lambda item: item.create_date, reverse=True)[:5]]

        return {
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'company_id': self.env.company.id,
            'currency': self.env.company.currency_id.name,
            'employees': len(employees),
            'active_contracts': Contract.search_count(contract_domain),
            'recruitments': Contract.search_count([('company_id', 'in', company_ids), ('date_start', '>=', date_from), ('date_start', '<=', date_to)] + ([('employee_id.department_id', '=', department_id)] if department_id else [])),
            'absences': len(validated_leaves),
            'leave_pending': Leave.search_count(leave_pending_domain),
            'leave_today': len(Leave.search(leave_today_domain).mapped('employee_id')),
            'leave_days': round(sum(validated_leaves.mapped('number_of_days')), 1),
            'attendance_count': len(attendances),
            'attendance_employees': len(attendances.mapped('employee_id')),
            'attendance_hours': round(sum(attendances.mapped('worked_hours')), 1),
            'attendance_open': Attendance.search_count(attendance_open_domain),
            'attendance_present_today': len(attendance_today.mapped('employee_id')),
            'attendance_rate': round((len(attendance_today.mapped('employee_id')) / len(employees) * 100), 1) if employees else 0.0,
            'attendance_panel_count': len(attendance_panel.mapped('employee_id')),
            'attendance_panel_hours': round(sum(attendance_panel.mapped('worked_hours')), 1),
            'payroll': _net_amount(slips),
            'payroll_gross': _gross_amount(slips),
            'payroll_count': len(slips),
            'payroll_average_net': round(_net_amount(slips) / len(slips), 0) if slips else 0.0,
            'payroll_to_process': Payslip.search_count([
                ('company_id', 'in', company_ids), ('state', 'in', ('draft', 'verify')),
                ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ] + ([('employee_id.department_id', '=', department_id)] if department_id else [])),
            'payroll_panel_total': _net_amount(payroll_panel),
            'payroll_panel_count': len(payroll_panel),
            'departments': [{'id': department.id, 'name': department.name} for department in departments],
            'distribution': distribution,
            'workforce_chart': workforce_chart,
            'payroll_chart': payroll_chart,
            'leave_distribution': leave_distribution,
            'recent_attendance': recent_attendance,
            'recent_leaves': recent_leaves,
            'chart': chart,
            'recent': recent,
        }

    def _compute_show_category(self):
        show_category = self.env['res.users'].has_group('hr.group_hr_user')
        for employee in self:
            if show_category or employee.user_id == self.env.user:
                employee.show_category = True
            else:
                employee.show_category = False

    def _get_seniority(self):
        """ Get the seniority's employee"""

        for employee in self:
            contract_obj = self.env['hr.contract']
            contract = contract_obj.search([('employee_id', '=', employee.id)], order='date_start asc', limit=1)
            contract_last = contract_obj.search([('employee_id', '=', employee.id)], order='date_start desc', limit=1)
            date_start = contract.date_start and datetime.strptime(contract.date_start, '%Y-%m-%d').date() or False
            date_end = contract_last.date_end and datetime.strptime(contract_last.date_end, '%Y-%m-%d').date() or False
            today = date.today()
            nb_years = 0
            nb_month = 0

            def diff_month(d1, d2):
                return (d1.year - d2.year) * 12 + d1.month - d2.month

            if date_start:
                if date_end and date_end < today:
                    end = date_end
                else:
                    end = today
                months = diff_month(end, date_start)
                nb_years = int(months/12)
                nb_month = months%12
                seniority = str(nb_years) + (nb_years not in (0,1) and _(" years ") or _(" year ")) + str(nb_month) + (nb_month not in (0,1) and _(" months") or _(" month"))
            else:
                seniority = _("0 year 0 month")

            employee.seniority = seniority
            employee.length_of_service = nb_years * 12 + nb_month

    def _get_nb_children(self):
        self.children = len(self.childs_ids)

    def name_get(self):
        res = []
        for employee in self:
            matrcule = employee.matricule and employee.matricule + ',' or ''
            res.append((employee.id, _("%s %s") % (matrcule, employee.name)))
        return res     

    def _get_age(self):
        for employee in self:
            birthday = employee.birthday and datetime.strptime(employee.birthday, '%Y-%m-%d').date() or False
            today = date.today()

            if birthday:
                age = (today - birthday).days
                age = int(age/365)
            else:
                age = 0

            employee.age = age


    def _get_hiring_date(self):
        contract = self.env['hr.contract']
        for employee in self:
            first_contract = contract.search([('employee_id', '=', employee.id)], order='date_start asc', limit=1)
            hiring_date = first_contract.date_start and datetime.strptime(first_contract.date_start, '%Y-%m-%d').date() or False

            employee.hired_date = hiring_date


    def _get_ending_date(self):
        contract = self.env['hr.contract']
        for employee in self:
            last_contract = contract.search([('employee_id', '=', employee.id)], order='date_start desc', limit=1)
            ending_date = last_contract.date_end and datetime.strptime(last_contract.date_end, '%Y-%m-%d').date() or False

            employee.ending_date = ending_date

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('matricule', operator, name)]
        employees = self.search(domain + args, limit=limit)
        return employees.name_get()
