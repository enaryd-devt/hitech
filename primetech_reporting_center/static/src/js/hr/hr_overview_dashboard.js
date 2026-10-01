/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getDefaultCustomDateRange, getGlobalDateFilter, globalDateFilterPayload, setGlobalDateFilter, subscribeToGlobalDateFilter } from "../services/dashboard_state_service";

export class HROverviewDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, ...getGlobalDateFilter(), departmentId: "", departmentOptions: [], data: {} });
        onWillStart(async () => {
            this.state.departmentOptions = await this.orm.searchRead("hr.department", [], ["name"]);
            await this.loadDashboard();
        });
        onMounted(() => {
            this._unsubscribeGlobalDateFilter = subscribeToGlobalDateFilter((filter) => {
                if (!this.isCurrentGlobalDateFilter(filter)) this.applyGlobalDateFilter(filter);
            });
            setTimeout(() => this.renderCharts(), 100);
        });
        onWillUnmount(() => this._unsubscribeGlobalDateFilter?.());
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.data = await this.orm.call("primetech.hr.dashboard", "get_dashboard_data", [{ ...globalDateFilterPayload(this.state), department_id: this.state.departmentId || false }]);
        this.state.loading = false;
        setTimeout(() => this.renderCharts(), 0);
    }

    isCurrentGlobalDateFilter(filter) {
        return ["period", "dateFrom", "dateTo"].every((key) => this.state[key] === filter[key]);
    }

    async applyGlobalDateFilter(filter) {
        Object.assign(this.state, filter);
        await this.loadDashboard();
    }

    async onGlobalPeriodChange(ev) {
        let next = { period: ev.target.value, dateFrom: this.state.dateFrom, dateTo: this.state.dateTo };
        if (next.period === "custom" && (!next.dateFrom || !next.dateTo)) {
            next = { ...next, ...getDefaultCustomDateRange() };
        }
        Object.assign(this.state, next);
        setGlobalDateFilter(next);
        await this.loadDashboard();
    }

    async onGlobalDateChange(field, ev) {
        const next = { period: this.state.period, dateFrom: this.state.dateFrom, dateTo: this.state.dateTo, [field]: ev.target.value };
        Object.assign(this.state, next);
        if (next.dateFrom && next.dateTo && next.dateFrom <= next.dateTo) {
            setGlobalDateFilter(next);
            await this.loadDashboard();
        }
    }

    async onDepartmentChange(ev) {
        this.state.departmentId = ev.target.value;
        await this.loadDashboard();
    }

    get domain() {
        return this.state.data.domains || {};
    }

    money(value) {
        return `${Math.round(value || 0).toLocaleString()} FCFA`;
    }

    pct(value) {
        return `${Number(value || 0).toFixed(1)}%`;
    }

    openView(name, resModel, domain = [], views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({ type: "ir.actions.act_window", name, res_model: resModel, views, view_mode: views.map((view) => view[1]).join(","), domain });
    }

    openEmployees(extraDomain = []) {
        this.openView("Employés", "hr.employee", [...(this.domain.employees || []), ...extraDomain]);
    }

    openContracts(extraDomain = []) {
        if (!this.state.data.supports_contracts) return this.openEmployees();
        this.openView("Contrats", "hr.contract", [...(this.domain.contracts || []), ...extraDomain]);
    }

    openLeaves(extraDomain = []) {
        if (!this.state.data.supports_leaves) return this.openEmployees();
        this.openView("Congés", "hr.leave", [...(this.domain.leaves || []), ...extraDomain]);
    }

    openAttendances(extraDomain = []) {
        if (!this.state.data.supports_attendances) return this.openEmployees();
        this.openView("Pointages", "hr.attendance", [...(this.domain.attendances || []), ...extraDomain]);
    }

    openPayroll(extraDomain = []) {
        if (!this.state.data.supports_payroll) return this.openEmployees();
        this.openView("Paie", "hr.payslip", [...(this.domain.payslips || []), ...extraDomain]);
    }

    renderCharts() {
        if (typeof Chart === "undefined") return;
        this.renderDepartmentChart();
        this.renderPresenceChart();
    }

    renderDepartmentChart() {
        const canvas = document.getElementById("hrDepartmentChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.department_cards || [];
        new Chart(canvas, { type: "doughnut", data: { labels: rows.map((row) => row.name), datasets: [{ data: rows.map((row) => row.percent), backgroundColor: ["#2563eb", "#16a34a", "#f97316", "#ef4444", "#7c3aed", "#0d9488"], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: "58%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } } } });
    }

    renderPresenceChart() {
        const canvas = document.getElementById("hrPresenceChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.presence_by_department || [];
        new Chart(canvas, { type: "bar", data: { labels: rows.map((row) => row.short_name), datasets: [{ label: "Présents", data: rows.map((row) => row.present), backgroundColor: "#14b8a6" }, { label: "Absents", data: rows.map((row) => row.absent), backgroundColor: "#ef4444" }, { label: "En congé", data: rows.map((row) => row.leave), backgroundColor: "#3b82f6" }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "top", align: "start" } }, scales: { y: { beginAtZero: true } } } });
    }
}
HROverviewDashboard.template = "primetech_reporting_center.HROverviewDashboard";
registry.category("actions").add("primetech_hr_overview_dashboard", HROverviewDashboard);
