/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getDefaultCustomDateRange, getGlobalDateFilter, globalDateFilterPayload, setGlobalDateFilter, subscribeToGlobalDateFilter } from "../services/dashboard_state_service";

export class PrimetechPurchaseOverviewDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, ...getGlobalDateFilter(), data: {} });
        onWillStart(async () => this.loadDashboard());
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
        this.state.data = await this.orm.call("primetech.purchase.overview", "get_dashboard_data", [globalDateFilterPayload(this.state)]);
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

    refresh() {
        return this.loadDashboard();
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

    openOrders(extraDomain = []) {
        this.openView("Commandes fournisseurs", "purchase.order", [...(this.domain.orders || []), ...extraDomain]);
    }

    openBills(extraDomain = []) {
        this.openView("Factures fournisseurs", "account.move", [...(this.domain.bills || []), ...extraDomain]);
    }

    openReceipts(extraDomain = []) {
        this.openView("Réceptions", "stock.picking", [...(this.domain.receipts || []), ...extraDomain]);
    }

    openSuppliers(ids = []) {
        this.openView("Fournisseurs", "res.partner", ids.length ? [["id", "in", ids]] : (this.domain.suppliers || []));
    }

    openProducts(ids = []) {
        this.openView("Produits", "product.product", ids.length ? [["id", "in", ids]] : []);
    }

    openWizard(xmlId) {
        this.action.doAction(xmlId);
    }

    renderCharts() {
        const data = this.state.data || {};
        this.renderDoughnut("pt_purchase_category_chart", data.expense_by_category || [], "category", "amount", ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#7c3aed"]);
        this.renderDoughnut("pt_purchase_orders_chart", data.order_reception_split || [], "label", "value", ["#2563eb", "#16a34a", "#f59e0b", "#ef4444"]);
    }

    renderDoughnut(canvasId, rows, labelKey, valueKey, colors) {
        if (typeof Chart === "undefined") return;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        new Chart(canvas, {
            type: "doughnut",
            data: { labels: rows.map((row) => row[labelKey]), datasets: [{ data: rows.map((row) => row[valueKey]), backgroundColor: colors, borderWidth: 0 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "58%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } } },
        });
    }
}

PrimetechPurchaseOverviewDashboard.template = "primetech_reporting_center.PurchaseOverviewDashboard";
registry.category("actions").add("primetech_purchase_overview_dashboard", PrimetechPurchaseOverviewDashboard);
export default PrimetechPurchaseOverviewDashboard;
