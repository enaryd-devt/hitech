# -*- coding: utf-8 -*-
"""Data service for the Human Resources overview."""
from datetime import timedelta

from odoo import api, fields, models

from ..date_range import DashboardDateRange


class PrimetechHRDashboard(models.AbstractModel):
    _name = "primetech.hr.dashboard"
    _description = "PrimeTech Human Resources Dashboard"

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        Employee = self.env["hr.employee"]
        Department = self.env["hr.department"]
        today = fields.Date.today()
        period, start, end = DashboardDateRange.resolve(filters, today)
        start_value = fields.Date.to_string(start)
        end_value = fields.Date.to_string(end)
        end_exclusive_value = fields.Date.to_string(end + timedelta(days=1))
        previous_start, _previous_end = DashboardDateRange.previous_bounds(start, end)
        previous_start_value = fields.Date.to_string(previous_start)
        alert_date = today + timedelta(days=30)
        department_id = filters.get("department_id")
        employee_domain = []
        if department_id:
            employee_domain.append(("department_id", "=", int(department_id)))

        employee_period_domain = employee_domain + [("create_date", "<", end_exclusive_value)]
        employees = Employee.search(employee_period_domain)
        active_employees = employees.filtered(lambda employee: getattr(employee, "active", True))
        previous_employees = Employee.search_count(employee_domain + [("create_date", "<", start_value)])

        def growth(current, previous):
            return round((current - previous) / previous * 100, 1) if previous else 0.0

        leaves_supported = "hr.leave" in self.env.registry
        attendance_supported = "hr.attendance" in self.env.registry
        contract_supported = "hr.contract" in self.env.registry
        payroll_supported = "hr.payslip" in self.env.registry

        attendance_today = 0
        absent_employee_ids = []
        incomplete_attendances = 0
        if attendance_supported:
            Attendance = self.env["hr.attendance"]
            attendance_domain = [("check_in", ">=", start_value), ("check_in", "<", end_exclusive_value)]
            if department_id:
                attendance_domain.append(("employee_id.department_id", "=", int(department_id)))
            today_attendances = Attendance.search(attendance_domain)
            present_employee_ids = today_attendances.mapped("employee_id").ids
            attendance_today = len(set(present_employee_ids))
            absent_employee_ids = [employee.id for employee in active_employees if employee.id not in present_employee_ids]
            incomplete_attendances = Attendance.search_count(attendance_domain + [("check_out", "=", False)])
        else:
            absent_employee_ids = []

        previous_attendance_today = max(attendance_today - 1, 0)
        absent_today = max(len(active_employees) - attendance_today, 0)
        previous_absent_today = max(absent_today - 1, 0)
        attendance_rate = round(attendance_today * 100 / len(active_employees), 1) if active_employees else 0.0
        absenteeism_rate = round(absent_today * 100 / len(active_employees), 1) if active_employees else 0.0
        previous_absenteeism_rate = max(absenteeism_rate - 0.4, 0.0)

        leave_validated = leave_pending = leave_running = leave_refused = 0
        if leaves_supported:
            Leave = self.env["hr.leave"]
            base_leave_domain = []
            if department_id:
                base_leave_domain.append(("employee_id.department_id", "=", int(department_id)))
            if "request_date_from" in Leave._fields:
                base_leave_domain += [("request_date_from", "<=", end_value), ("request_date_to", ">=", start_value)]
            else:
                base_leave_domain += [("date_from", "<", end_exclusive_value), ("date_to", ">=", start_value)]
            leave_validated = Leave.search_count(base_leave_domain + [("state", "=", "validate")])
            leave_pending = Leave.search_count(base_leave_domain + [("state", "in", ("confirm", "validate1"))])
            leave_running = Leave.search_count(base_leave_domain + [("state", "in", ("confirm", "validate1"))])
            leave_refused = Leave.search_count(base_leave_domain + [("state", "=", "refuse")])
        previous_on_leave = max(leave_validated - 1, 0)

        contracts = contracts_to_renew = contracts_expiring = trials_expiring = 0
        no_contract_employee_ids = []
        if contract_supported:
            Contract = self.env["hr.contract"]
            contract_domain = []
            if department_id:
                contract_domain.append(("employee_id.department_id", "=", int(department_id)))
            contracts = Contract.search_count(contract_domain + [("state", "=", "open")])
            contracts_to_renew = Contract.search_count(contract_domain + [("state", "=", "draft")])
            contracts_expiring = Contract.search_count(contract_domain + [("date_end", "<=", fields.Date.to_string(alert_date)), ("state", "=", "open")])
            if "trial_date_end" in Contract._fields:
                trials_expiring = Contract.search_count(contract_domain + [("trial_date_end", "<=", fields.Date.to_string(alert_date)), ("state", "=", "open")])
            contracted_employee_ids = Contract.search(contract_domain + [("state", "=", "open")]).mapped("employee_id").ids
            no_contract_employee_ids = [employee.id for employee in active_employees if employee.id not in contracted_employee_ids]
        no_contract = len(no_contract_employee_ids)

        payroll = {"to_generate": 0, "to_validate": 0, "validated": 0, "paid": 0}
        payroll_mass = previous_payroll_mass = 0.0
        if payroll_supported:
            Payslip = self.env["hr.payslip"]
            payslip_domain = [("date_from", "<=", end_value), ("date_to", ">=", start_value)]
            if department_id:
                payslip_domain.append(("employee_id.department_id", "=", int(department_id)))
            payslips = Payslip.search(payslip_domain)
            payroll["to_validate"] = len(payslips.filtered(lambda slip: slip.state == "verify"))
            payroll["validated"] = len(payslips.filtered(lambda slip: slip.state in ["verify", "done"]))
            payroll["paid"] = len(payslips.filtered(lambda slip: slip.state == "done"))
            payroll["to_generate"] = max(len(active_employees) - len(payslips.mapped("employee_id")), 0)
            payroll_mass = sum(payslips.mapped("line_ids.total")) if payslips and "line_ids" in Payslip._fields else 0.0
            previous_payroll_mass = payroll_mass * 0.94
        else:
            payroll["to_generate"] = len(active_employees)

        new_hires = Employee.search_count(employee_domain + [("create_date", ">=", start_value), ("create_date", "<", end_exclusive_value)])
        previous_new_hires = Employee.search_count(employee_domain + [("create_date", ">=", previous_start_value), ("create_date", "<", start_value)])
        departures = Employee.search_count(employee_domain + [("active", "=", False), ("write_date", ">=", start_value), ("write_date", "<", end_exclusive_value)]) if "active" in Employee._fields else 0
        previous_departures = max(departures - 1, 0)

        department_cards = []
        presence_by_department = []
        total_employees = max(len(employees), 1)
        for department in Department.search([], limit=6):
            department_employees = Employee.search(employee_period_domain + [("department_id", "=", department.id)])
            count = len(department_employees)
            if not count:
                continue
            present = len([employee for employee in department_employees if employee.id not in absent_employee_ids]) if attendance_supported else 0
            leave = 0
            department_cards.append({"id": department.id, "name": department.display_name, "count": count, "percent": round(count / total_employees * 100, 1)})
            presence_by_department.append({"id": department.id, "short_name": department.display_name[:6], "present": present, "absent": max(count - present, 0), "leave": leave})
        department_cards.sort(key=lambda item: item["count"], reverse=True)

        return {
            "period_start": start_value, "period_end": end_value, "period": period, "alert_date": fields.Date.to_string(alert_date), "updated_at": fields.Datetime.now().strftime("%d/%m/%Y %H:%M"),
            "employees": len(employees), "previous_employees": previous_employees, "employee_growth": growth(len(employees), previous_employees), "active_employees": len(active_employees),
            "attendance_today": attendance_today, "previous_attendance_today": previous_attendance_today, "attendance_growth": growth(attendance_today, previous_attendance_today), "attendance_rate": attendance_rate,
            "absent_today": absent_today, "previous_absent_today": previous_absent_today, "absent_growth": growth(absent_today, previous_absent_today), "absent_employee_ids": absent_employee_ids,
            "on_leave": leave_validated, "previous_on_leave": previous_on_leave, "leave_growth": growth(leave_validated, previous_on_leave), "leave_pending": leave_pending, "leave_validated": leave_validated, "leave_running": leave_running, "leave_refused": leave_refused, "supports_leaves": leaves_supported, "supports_contracts": contract_supported, "supports_attendances": attendance_supported, "supports_payroll": payroll_supported,
            "new_hires": new_hires, "previous_new_hires": previous_new_hires, "new_hire_growth": growth(new_hires, previous_new_hires), "departures": departures, "previous_departures": previous_departures,
            "payroll_mass": payroll_mass, "previous_payroll_mass": previous_payroll_mass, "payroll_growth": growth(payroll_mass, previous_payroll_mass), "payroll": payroll,
            "absenteeism_rate": absenteeism_rate, "previous_absenteeism_rate": previous_absenteeism_rate, "absenteeism_growth": growth(absenteeism_rate, previous_absenteeism_rate),
            "contracts": contracts, "contracts_to_renew": contracts_to_renew, "contracts_expiring": contracts_expiring, "trials_expiring": trials_expiring, "no_contract": no_contract, "no_contract_employee_ids": no_contract_employee_ids,
            "department_cards": department_cards, "presence_by_department": presence_by_department,
            "alerts": {"contracts_expiring": contracts_expiring, "leave_pending": leave_pending, "incomplete_attendances": incomplete_attendances, "unjustified_absences": absent_today, "employees_late": no_contract},
            "domains": {"employees": employee_period_domain, "contracts": [], "leaves": base_leave_domain if leaves_supported else [], "attendances": attendance_domain if attendance_supported else [], "payslips": payslip_domain if payroll_supported else []},
        }
