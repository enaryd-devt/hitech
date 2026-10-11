/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PayrollDashboard extends Component {
    static template = "payroll.PayrollDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const saved = this.readState();
        const allowedPeriods = ["quarter", "semester", "year", "custom"];
        const hasValidSavedPeriod = allowedPeriods.includes(saved.period);
        const period = hasValidSavedPeriod ? saved.period : "quarter";
        const range = this.periodRange(period);
        this.state = useState({
            loading: true,
            period,
            dateFrom: (hasValidSavedPeriod && saved.dateFrom) || range.dateFrom,
            dateTo: (hasValidSavedPeriod && saved.dateTo) || range.dateTo,
            data: null,
        });
        onWillStart(() => this.loadData());
    }

    readState() {
        try {
            return JSON.parse(sessionStorage.getItem("payroll_dashboard_state") || "{}");
        } catch {
            return {};
        }
    }

    saveState() {
        sessionStorage.setItem("payroll_dashboard_state", JSON.stringify({
            period: this.state.period,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
        }));
    }

    toISO(value) {
        const year = value.getFullYear();
        const month = String(value.getMonth() + 1).padStart(2, "0");
        const day = String(value.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    periodRange(period) {
        const today = new Date();
        let first;
        let last;
        if (period === "quarter") {
            const month = Math.floor(today.getMonth() / 3) * 3;
            first = new Date(today.getFullYear(), month, 1);
            last = new Date(today.getFullYear(), month + 3, 0);
        } else if (period === "semester") {
            const month = today.getMonth() < 6 ? 0 : 6;
            first = new Date(today.getFullYear(), month, 1);
            last = new Date(today.getFullYear(), month + 6, 0);
        } else if (period === "year") {
            first = new Date(today.getFullYear(), 0, 1);
            last = new Date(today.getFullYear(), 11, 31);
        } else {
            const month = Math.floor(today.getMonth() / 3) * 3;
            first = new Date(today.getFullYear(), month, 1);
            last = new Date(today.getFullYear(), month + 3, 0);
        }
        return { dateFrom: this.toISO(first), dateTo: this.toISO(last) };
    }

    async loadData() {
        if (!this.state.dateFrom || !this.state.dateTo || this.state.dateFrom > this.state.dateTo) {
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "hr.payslip",
                "get_payroll_dashboard_data",
                [this.state.dateFrom, this.state.dateTo]
            );
            this.saveState();
        } catch (error) {
            this.notification.add(
                error.message || "Impossible de charger le tableau de bord de la paie.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    onPeriodChange(event) {
        this.state.period = event.target.value;
        if (this.state.period !== "custom") {
            const range = this.periodRange(this.state.period);
            this.state.dateFrom = range.dateFrom;
            this.state.dateTo = range.dateTo;
            this.loadData();
        }
    }

    onDateChange(field, event) {
        this.state[field] = event.target.value;
        this.loadData();
    }

    formatMoney(value) {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: this.state.data?.currency || "XAF",
            maximumFractionDigits: 0,
        }).format(value || 0);
    }

    formatNumber(value) {
        return new Intl.NumberFormat().format(value || 0);
    }

    formatDate(value) {
        if (!value) {
            return "";
        }
        const [year, month, day] = value.split("-");
        return `${day}/${month}/${year}`;
    }

    get donutStyle() {
        const items = this.state.data?.statuses || [];
        let cursor = 0;
        const stops = [];
        for (const item of items) {
            const end = cursor + item.percent;
            stops.push(`${item.color} ${cursor}% ${end}%`);
            cursor = end;
        }
        if (cursor < 100) {
            stops.push(`var(--o-gray-200, #e9ecef) ${cursor}% 100%`);
        }
        return `background: conic-gradient(${stops.join(",")})`;
    }

    baseDomain() {
        return [
            ["company_id", "=", this.state.data?.company_id],
            ["date_to", ">=", this.state.dateFrom],
            ["date_to", "<=", this.state.dateTo],
        ];
    }

    openAction(model, domain, name, resId = false) {
        const action = {
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: resId ? [[false, "form"]] : [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        };
        if (resId) {
            action.res_id = resId;
        }
        return this.action.doAction(action);
    }

    openPayslips(extraDomain = [], name = "Bulletins de paie") {
        return this.openAction("hr.payslip", [...this.baseDomain(), ...extraDomain], name);
    }

    openAll() {
        return this.openPayslips([], "Bulletins de la période");
    }

    openValidated() {
        return this.openPayslips([["state", "=", "done"], ["credit_note", "=", false]], "Bulletins validés");
    }

    openState(state, label) {
        return this.openPayslips([["state", "=", state]], label);
    }

    openEmployees() {
        return this.openAction(
            "hr.employee",
            [["id", "in", this.state.data?.employee_ids || []]],
            "Salariés payés"
        );
    }

    openEmployee(item) {
        return this.openPayslips(
            [["employee_id", "=", item.id], ["state", "=", "done"]],
            `Bulletins - ${item.name}`
        );
    }

    openDepartment(item) {
        const domain = item.id
            ? [["employee_id.department_id", "=", item.id]]
            : [["employee_id.department_id", "=", false]];
        return this.openPayslips([...domain, ["state", "=", "done"]], `Paie - ${item.name}`);
    }

    openEvolution(point) {
        return this.openAction("hr.payslip", [
            ["company_id", "=", this.state.data?.company_id],
            ["date_to", ">=", point.date_from],
            ["date_to", "<=", point.date_to],
            ["state", "=", "done"],
        ], `Paie - ${point.label}`);
    }

    openPayslip(item) {
        return this.openAction("hr.payslip", [], item.name, item.id);
    }
}

registry.category("actions").add("payroll_dashboard", PayrollDashboard);
