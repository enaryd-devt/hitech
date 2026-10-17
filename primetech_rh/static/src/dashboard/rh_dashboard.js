/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class OrickRhDashboard extends Component {
    static template = "primetech_rh.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.root = useRef("rhDashboardRoot");
        const saved = this.readState();
        this.restoreScroll = saved?.scrollTop || 0;
        this.state = useState({
            loading: true,
            data: { departments: [], distribution: [], chart: [], recent: [], workforce_chart: [], payroll_chart: [], leave_distribution: [] },
            filters: { period: "month", department_id: "", date_from: "", date_to: "", workforce_period: "year", attendance_period: "month", leave_period: "year", payroll_period: "year", ...(saved?.filters || {}) },
        });
        this.load = this.load.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.openList = this.openList.bind(this);
        this.openEmployee = this.openEmployee.bind(this);
        this.openDepartment = this.openDepartment.bind(this);
        this.openEmployees = this.openEmployees.bind(this);
        this.openContracts = this.openContracts.bind(this);
        this.openAbsences = this.openAbsences.bind(this);
        this.openAttendances = this.openAttendances.bind(this);
        this.openAttendanceOpen = this.openAttendanceOpen.bind(this);
        this.openLeavePending = this.openLeavePending.bind(this);
        this.openLeaveToday = this.openLeaveToday.bind(this);
        this.openPayslips = this.openPayslips.bind(this);
        this.openPayrollToProcess = this.openPayrollToProcess.bind(this);
        this.openBucket = this.openBucket.bind(this);
        this.create = this.create.bind(this);
        onWillStart(() => this.load());
        onMounted(() => {
            if (this.restoreScroll) requestAnimationFrame(() => { this.root.el.scrollTop = this.restoreScroll; });
        });
        onWillUnmount(() => this.saveState());
    }
    readState() {
        try { return JSON.parse(window.sessionStorage.getItem("orick_rh_dashboard_state") || "null"); } catch { return null; }
    }
    saveState() {
        try { window.sessionStorage.setItem("orick_rh_dashboard_state", JSON.stringify({ filters: { ...this.state.filters }, scrollTop: this.root.el?.scrollTop || 0 })); } catch { /* stockage facultatif */ }
    }
    async load() {
        this.state.loading = true;
        try { this.state.data = await this.orm.call("hr.employee", "get_rh_dashboard_data", [this.state.filters]); }
        finally { this.state.loading = false; }
    }
    onFilterChange(event) {
        if (event?.target?.value === "custom" && !this.state.filters.date_from) {
            this.state.filters.date_from = this.state.data.date_from || "";
            this.state.filters.date_to = this.state.data.date_to || "";
        }
        this.saveState();
        return this.load();
    }
    money(value) { return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value || 0)} ${this.state.data.currency || "FCFA"}`; }
    maxPayroll() { return Math.max(1, ...this.state.data.chart.map((item) => item.payroll || 0)); }
    bar(value) { return `${Math.max(2, ((value || 0) / this.maxPayroll()) * 100)}%`; }
    distributionWidth(value) { return `${Math.max(8, ((value || 0) / Math.max(1, this.state.data.employees)) * 100)}%`; }
    leaveWidth(value) {
        const maximum = Math.max(1, ...this.state.data.leave_distribution.map((item) => item.days || 0));
        return `${Math.max(8, ((value || 0) / maximum) * 100)}%`;
    }
    chartPoints(items, key) {
        const values = items.map((item) => Number(item[key]) || 0);
        const maximum = Math.max(1, ...values);
        return values.map((value, index) => {
            const x = values.length <= 1 ? 50 : (index / (values.length - 1)) * 100;
            const y = 91 - ((value / maximum) * 75);
            return `${x},${y}`;
        }).join(" ");
    }
    chartLast(items, key) { return items.length ? (items[items.length - 1][key] || 0) : 0; }
    chartSum(items, key) { return items.reduce((total, item) => total + (Number(item[key]) || 0), 0); }
    chartLabel(item, index) { return item.label; }
    departmentDomain(extra = []) {
        const domain = [["active", "=", true]];
        if (this.state.filters.department_id) domain.push(["department_id", "=", Number(this.state.filters.department_id)]);
        return domain.concat(extra);
    }
    payslipDomain(dateFrom = this.state.data.date_from, dateTo = this.state.data.date_to) {
        const domain = [["date_to", ">=", dateFrom], ["date_to", "<=", dateTo], ["state", "in", ["done", "paid"]]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return domain;
    }
    openList(model, domain = [], name = "") {
        this.saveState();
        return this.action.doAction({ type: "ir.actions.act_window", name, res_model: model, views: [[false, "list"], [false, "form"]], domain, target: "current" });
    }
    openEmployees() { return this.openList("hr.employee", this.departmentDomain(), _t("Effectif")); }
    openContracts(kind = "active") {
        const domain = kind === "recruitment"
            ? [["date_start", ">=", this.state.data.date_from], ["date_start", "<=", this.state.data.date_to]]
            : [["state", "=", "open"]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return this.openList("hr.contract", domain, kind === "recruitment" ? _t("Nouveaux recrutements") : _t("Contrats actifs"));
    }
    openAbsences() {
        const domain = [["date_from", "<=", this.state.data.date_to], ["date_to", ">=", this.state.data.date_from], ["state", "in", ["validate", "validate1"]]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return this.openList("hr.leave", domain, "Absences validées");
    }
    attendanceDomain(extra = []) {
        const from = `${this.state.data.date_from} 00:00:00`;
        const until = new Date(`${this.state.data.date_to}T00:00:00`);
        until.setDate(until.getDate() + 1);
        const to = `${until.toISOString().slice(0, 10)} 00:00:00`;
        const domain = [["check_in", ">=", from], ["check_in", "<", to]];
        if (this.state.filters.department_id) domain.push(["department_id", "=", Number(this.state.filters.department_id)]);
        return domain.concat(extra);
    }
    openAttendances() { return this.openList("hr.attendance", this.attendanceDomain(), _t("Présences")); }
    openAttendanceOpen() {
        const domain = [["check_out", "=", false]];
        if (this.state.filters.department_id) domain.push(["department_id", "=", Number(this.state.filters.department_id)]);
        return this.openList("hr.attendance", domain, _t("Pointages en cours"));
    }
    leaveDomain(extra = []) {
        const domain = [["request_date_from", "<=", this.state.data.date_to], ["request_date_to", ">=", this.state.data.date_from]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return domain.concat(extra);
    }
    openLeavePending() { return this.openList("hr.leave", this.leaveDomain([["state", "in", ["confirm", "validate1"]]]), _t("Congés en attente")); }
    openLeaveToday() {
        const today = new Date().toISOString().slice(0, 10);
        const domain = [["date_from", "<=", today], ["date_to", ">=", today], ["state", "=", "validate"]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return this.openList("hr.leave", domain, _t("Absents aujourd’hui"));
    }
    openPayslips() { return this.openList("hr.payslip", this.payslipDomain(), _t("Masse salariale")); }
    openPayrollToProcess() {
        const domain = [["date_to", ">=", this.state.data.date_from], ["date_to", "<=", this.state.data.date_to], ["state", "in", ["draft", "verify"]]];
        if (this.state.filters.department_id) domain.push(["employee_id.department_id", "=", Number(this.state.filters.department_id)]);
        return this.openList("hr.payslip", domain, _t("Bulletins à traiter"));
    }
    openDepartment(item) { return this.openList("hr.employee", this.departmentDomain(item.id ? [["department_id", "=", item.id]] : [["department_id", "=", false]]), item.name); }
    openBucket(item) { return this.openList("hr.payslip", this.payslipDomain(item.date_from, item.date_to), `Paie - ${item.label}`); }
    openEmployee(item) {
        this.saveState();
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "hr.payslip", res_id: item.id, views: [[false, "form"]], target: "current" });
    }
    create(model, name) {
        this.saveState();
        return this.action.doAction({ type: "ir.actions.act_window", name, res_model: model, views: [[false, "form"]], target: "current" });
    }
}

registry.category("actions").add("primetech_rh.dashboard", OrickRhDashboard);
