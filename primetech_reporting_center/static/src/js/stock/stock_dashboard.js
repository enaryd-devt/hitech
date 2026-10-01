/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { getDefaultCustomDateRange, getGlobalDateFilter, globalDateFilterPayload, setGlobalDateFilter, subscribeToGlobalDateFilter } from "../services/dashboard_state_service";

export class StockDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.state = useState({ loading: true, ...getGlobalDateFilter(), warehouseSort: "value_desc", data: {} });
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
        this.state.data = await rpc("/primetech/stock/dashboard", globalDateFilterPayload(this.state));
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

    openSettings() {
        this.action.doAction("base_setup.action_general_configuration");
    }

    get theme() {
        return this.state.data.settings || {};
    }

    get dashboardStyle() {
        return this.theme.theme_primary_color ? `--pt-primary: ${this.theme.theme_primary_color}; --o-brand-primary: ${this.theme.theme_primary_color};` : "";
    }

    get dashboardClass() {
        return `pt-stock-overview pt-kpi-${this.theme.theme_kpi_style || "cards"}`;
    }

    onWarehouseSortChange(ev) {
        this.state.warehouseSort = ev.target.value;
    }

    sortedWarehouses() {
        const rows = [...(this.state.data.warehouses || [])];
        const sort = this.state.warehouseSort;
        if (sort === "name_asc") {
            return rows.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
        }
        if (sort === "date_desc") {
            return rows.sort((a, b) => (b.latest_move || "").localeCompare(a.latest_move || ""));
        }
        if (sort === "value_asc") {
            return rows.sort((a, b) => (a.value || 0) - (b.value || 0));
        }
        return rows.sort((a, b) => (b.value || 0) - (a.value || 0));
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

    openProducts(extraDomain = []) {
        this.openView("Produits", "product.product", [...(this.domain.products || []), ...extraDomain]);
    }

    openLocations(extraDomain = []) {
        this.openView("Emplacements", "stock.location", [...(this.domain.locations || []), ...extraDomain]);
    }

    openTransfers(extraDomain = []) {
        this.openView("Transferts", "stock.picking", [...(this.domain.pickings || []), ...extraDomain]);
    }

    openMoves(extraDomain = []) {
        this.openView("Mouvements de stock", "stock.move", [...(this.domain.moves || []), ...extraDomain]);
    }

    openReplenishments(extraDomain = []) {
        this.openView("Demandes de réapprovisionnement", "product.product", extraDomain.length ? extraDomain : (this.domain.orderpoints || []));
    }

    renderCharts() {
        if (typeof Chart === "undefined") return;
        const canvas = document.getElementById("stockMovementsChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.data.period_moves || [];
        new Chart(canvas, {
            type: this.theme.theme_chart_format || "line",
            data: {
                labels: rows.map((row) => row.label),
                datasets: [
                    { label: "Entrées", data: rows.map((row) => row.incoming), borderColor: "#2563eb", backgroundColor: "#2563eb", tension: 0.35 },
                    { label: "Sorties", data: rows.map((row) => row.outgoing), borderColor: "#ef4444", backgroundColor: "#ef4444", tension: 0.35 },
                    { label: "Transferts", data: rows.map((row) => row.internal), borderColor: "#16a34a", backgroundColor: "#16a34a", tension: 0.35 },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "top", align: "start" } }, interaction: { intersect: false, mode: "index" } },
        });
    }
}

StockDashboard.template = "primetech_reporting_center.StockDashboard";
registry.category("actions").add("primetech_stock_dashboard", StockDashboard);
