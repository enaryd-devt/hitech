/** @odoo-module **/

import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class LogisticsCommandCenter extends Component {
    setup() {
        this.action = useService("action");
        this.state = useState({ loading: true, transfers_by_state: [], procurement_requests: [], customer_orders: [], fleet: { vehicles: 0, drivers: 0 }, warehouse_load: [], alerts: { stockouts: 0, below_min: 0, overstock: 0 }, kpis: {}, domains: {}, urgent_transfers: [], top_products_to_replenish: [], carrier_workload: [] });
        onWillStart(async () => this.loadData());
        onMounted(() => setTimeout(() => this.renderCharts(), 100));
    }

    async loadData() {
        this.state.loading = true;
        const data = await rpc("/web/dataset/call_kw", { model: "pt.stock.dashboard", method: "get_logistics_command_center", args: [], kwargs: {} });
        Object.assign(this.state, data, { loading: false });
        setTimeout(() => this.renderCharts(), 0);
    }

    openView(name, resModel, domain = [], views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({ type: "ir.actions.act_window", name, res_model: resModel, views, view_mode: views.map((view) => view[1]).join(","), domain });
    }

    openTransfers(extraDomain = []) {
        this.openView("Bons de transfert", "stock.picking", [...(this.state.domains.pickings || []), ...extraDomain]);
    }

    openProducts(extraDomain = []) {
        this.openView("Produits", "product.product", [...(this.state.domains.products || []), ...extraDomain]);
    }

    openWarehouses(extraDomain = []) {
        this.openView("Entrepôts", "stock.warehouse", extraDomain);
    }

    openMoves(extraDomain = []) {
        this.openView("Mouvements de stock", "stock.move", [...(this.state.domains.moves || []), ...extraDomain]);
    }

    renderCharts() {
        if (typeof Chart === "undefined") return;
        this.renderStatusChart();
        this.renderWarehouseChart();
    }

    renderStatusChart() {
        const canvas = document.getElementById("logisticsStatusChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        new Chart(canvas, { type: "doughnut", data: { labels: this.state.transfers_by_state.map((row) => row.label), datasets: [{ data: this.state.transfers_by_state.map((row) => row.count), backgroundColor: ["#64748b", "#f59e0b", "#2563eb", "#16a34a", "#0d9488", "#ef4444"], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: "58%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } } } });
    }

    renderWarehouseChart() {
        const canvas = document.getElementById("logisticsWarehouseChart");
        if (!canvas) return;
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        const rows = this.state.warehouse_load || [];
        new Chart(canvas, { type: "bar", data: { labels: rows.map((row) => row.name), datasets: [{ label: "En cours", data: rows.map((row) => row.in_progress), backgroundColor: "#2563eb" }, { label: "En attente", data: rows.map((row) => row.waiting), backgroundColor: "#f59e0b" }, { label: "Terminées", data: rows.map((row) => row.completed), backgroundColor: "#16a34a" }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "top", align: "start" } }, scales: { y: { beginAtZero: true } } } });
    }
}

LogisticsCommandCenter.template = "primetech_reporting_center.LogisticsCommandCenter";
registry.category("actions").add("primetech_logistics_command_center", LogisticsCommandCenter);
