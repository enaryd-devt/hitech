/** @odoo-module **/
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { getDefaultCustomDateRange, getGlobalDateFilter, globalDateFilterPayload, setGlobalDateFilter, subscribeToGlobalDateFilter } from "../services/dashboard_state_service";

export class AccountingDashboard extends Component {
    static props = { "*": true };
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const dateFilter = getGlobalDateFilter();
        this.state = useState({ loading: true, dateFilter, filters: { company_id: "", period: dateFilter.period, comparison: "previous_period" }, data: {} });
        onWillStart(() => this.loadData());
        onMounted(() => {
            this._unsubscribeGlobalDateFilter = subscribeToGlobalDateFilter((filter) => {
                if (!this.isCurrentGlobalDateFilter(filter)) this.applyGlobalDateFilter(filter);
            });
            this.scheduleChartRender();
        });
        onWillUnmount(() => {
            this._unsubscribeGlobalDateFilter?.();
            if (this._chartRenderFrame) cancelAnimationFrame(this._chartRenderFrame);
        });
    }

    async loadData() {
        this.state.loading = true;
        const filters = { ...this.state.filters, ...globalDateFilterPayload(this.state.dateFilter) };
        this.state.data = await this.orm.call("primetech.accounting.dashboard", "get_overview_data", [filters]);
        this.state.filters = { ...this.state.filters, ...(this.state.data.filters || {}) };
        this.state.loading = false;
        this.scheduleChartRender();
    }

    scheduleChartRender() {
        if (this._chartRenderFrame) cancelAnimationFrame(this._chartRenderFrame);
        this._chartRenderFrame = requestAnimationFrame(() => {
            this._chartRenderFrame = null;
            this.renderCharts();
        });
    }

    async onFilterChange(key, ev) {
        this.state.filters[key] = ev.target.value;
        await this.loadData();
    }

    isCurrentGlobalDateFilter(filter) {
        return ["period", "dateFrom", "dateTo"].every((key) => this.state.dateFilter[key] === filter[key]);
    }

    async applyGlobalDateFilter(filter) {
        this.state.dateFilter = { ...filter };
        this.state.filters.period = filter.period;
        await this.loadData();
    }

    async onGlobalPeriodChange(ev) {
        let next = { ...this.state.dateFilter, period: ev.target.value };
        if (next.period === "custom" && (!next.dateFrom || !next.dateTo)) {
            next = { ...next, ...getDefaultCustomDateRange() };
        }
        this.state.dateFilter = next;
        this.state.filters.period = next.period;
        setGlobalDateFilter(next);
        await this.loadData();
    }

    async onGlobalDateChange(field, ev) {
        const next = { ...this.state.dateFilter, [field]: ev.target.value };
        this.state.dateFilter = next;
        if (next.dateFrom && next.dateTo && next.dateFrom <= next.dateTo) {
            setGlobalDateFilter(next);
            await this.loadData();
        }
    }

    async onCompanyChange(ev) {
        await this.onFilterChange("company_id", ev);
    }

    async onComparisonChange(ev) {
        await this.onFilterChange("comparison", ev);
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

    openInvoices(extraDomain = []) {
        this.openView("Factures clients", "account.move", [...(this.domain.customer_invoices || []), ...extraDomain]);
    }

    openBills(extraDomain = []) {
        this.openView("Factures fournisseurs", "account.move", [...(this.domain.vendor_bills || []), ...extraDomain]);
    }

    openAccounts(extraDomain = []) {
        this.openView("Comptes", "account.account", [...(this.domain.cash_accounts || []), ...extraDomain]);
    }

    openJournalItems(extraDomain = []) {
        this.openView("Écritures comptables", "account.move.line", [...(this.domain.move_lines || []), ...extraDomain]);
    }

    openPartners(ids = []) {
        this.openView("Clients", "res.partner", ids.length ? [["id", "in", ids]] : []);
    }

    openTrialBalance() {
        this.action.doAction("primetech_reporting_center.action_trial_balance_wizard");
    }

    renderCharts() {
        if (typeof Chart === "undefined") return;
        this.renderTreasuryChart();
        this.renderCashChart();
        this.renderAgeChart();
    }

    renderTreasuryChart() {
        const canvas = document.getElementById("accountingTreasuryChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.treasury_evolution || [];
        new Chart(canvas, {
            type: "bar",
            data: {
                labels: rows.map((row) => row.label),
                datasets: [
                    { type: "bar", label: "Encaissements", data: rows.map((row) => row.incoming), backgroundColor: "#60a5fa", borderRadius: 3, borderSkipped: false, barPercentage: .72, categoryPercentage: .72 },
                    { type: "bar", label: "Décaissements", data: rows.map((row) => -(row.outgoing || 0)), backgroundColor: "#fda4af", borderRadius: 3, borderSkipped: false, barPercentage: .72, categoryPercentage: .72 },
                    { type: "line", label: "Solde cumulé", data: rows.map((row) => row.balance), borderColor: "#08965a", backgroundColor: "rgba(8, 150, 90, .11)", fill: true, tension: .28, borderWidth: 2, pointRadius: 0, pointHoverRadius: 3 },
                ],
            },
            options: {
                animation: false,
                parsing: false,
                normalized: true,
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: { legend: { position: "top", align: "start", labels: { boxWidth: 8, boxHeight: 8, padding: 10, font: { size: 10 } } } },
                scales: {
                    x: { grid: { display: false }, ticks: { autoSkip: true, maxTicksLimit: 8, font: { size: 9 } } },
                    y: { grid: { color: "rgba(148, 163, 184, .18)" }, ticks: { maxTicksLimit: 4, font: { size: 9 } } },
                },
            },
        });
    }

    renderCashChart() {
        const canvas = document.getElementById("accountingCashChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.cash_accounts || [];
        new Chart(canvas, { type: "doughnut", data: { labels: rows.map((row) => row.name), datasets: [{ data: rows.map((row) => row.amount), backgroundColor: ["#2563eb", "#16a34a", "#f97316", "#f59e0b", "#7c3aed", "#0891b2", "#e11d48", "#64748b"], borderWidth: 0 }] }, options: { animation: false, parsing: false, normalized: true, events: [], responsive: true, maintainAspectRatio: false, cutout: "58%", plugins: { legend: { display: false } } } });
    }

    renderAgeChart() {
        const canvas = document.getElementById("accountingAgeChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.receivable_aging || [];
        new Chart(canvas, { type: "doughnut", data: { labels: rows.map((row) => row.label), datasets: [{ data: rows.map((row) => row.amount), backgroundColor: ["#2563eb", "#f59e0b", "#ef4444", "#7c3aed"], borderWidth: 0 }] }, options: { animation: false, parsing: false, normalized: true, events: [], responsive: true, maintainAspectRatio: false, cutout: "58%", plugins: { legend: { display: false } } } });
    }
}
AccountingDashboard.template = "primetech_reporting_center.AccountingDashboard";
