/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PrimetechStockDashboard extends Component {
    static template = "primetech_product_stock_dashboard.StockDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, companyId: "all", warehouseId: "all", data: null });
        onWillStart(async () => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("product.template", "get_primetech_stock_dashboard_data", [{
            company_id: this.state.companyId === "all" ? false : this.state.companyId,
            warehouse_id: this.state.warehouseId === "all" ? false : this.state.warehouseId,
        }]);
        this.state.companyId = String(this.state.data.selected_company_id || "all");
        this.state.warehouseId = String(this.state.data.selected_warehouse_id || "all");
        this.state.loading = false;
    }

    async onCompanyChange(ev) {
        this.state.companyId = ev.target.value || "all";
        this.state.warehouseId = "all";
        await this.load();
    }

    async onWarehouseChange(ev) {
        this.state.warehouseId = ev.target.value || "all";
        await this.load();
    }

    formatNumber(value) {
        return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value || 0);
    }

    formatMoney(value) {
        const text = this.formatNumber(value);
        return this.state.data.currency_position === "before" ? `${this.state.data.currency} ${text}` : `${text} ${this.state.data.currency}`;
    }

    openProducts(domain = []) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Articles",
            res_model: "product.template",
            views: [[false, "list"], [false, "form"], [false, "kanban"]],
            domain,
        });
    }

    openProduct(product) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: product.id,
            views: [[false, "form"]],
        });
    }

    openMove(move) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.move",
            res_id: move.id,
            views: [[false, "form"]],
        });
    }

    openCategory(category, alertOnly = false) {
        const domain = [["categ_id", "=", category.id]];
        if (alertOnly) {
            domain.push(["primetech_stock_level", "in", ["warning", "critical"]]);
        }
        return this.openProducts(domain);
    }

    openKpi(kpi) {
        if (kpi.tone === "orange") {
            return this.openTransfersByCode("incoming");
        }
        if (kpi.tone === "violet") {
            return this.openTransfersByCode("outgoing");
        }
        if (kpi.tone === "red") {
            return this.action.doAction({
                type: "ir.actions.act_window", name: "Opérations en retard", res_model: "stock.picking",
                views: [[false, "list"], [false, "form"]],
                domain: [["scheduled_date", "<", new Date().toISOString()], ["state", "not in", ["done", "cancel"]]],
            });
        }
        return this.openProducts();
    }

    openTransfersByCode(code) {
        return this.action.doAction({
            type: "ir.actions.act_window", name: code === "incoming" ? "Réceptions à traiter" : "Livraisons à traiter",
            res_model: "stock.picking", views: [[false, "list"], [false, "form"]],
            domain: [["picking_type_code", "=", code], ["state", "not in", ["done", "cancel"]]],
        });
    }

    openOperation(operation) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: operation.name,
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain: [["picking_type_id", "=", operation.id], ["state", "not in", ["done", "cancel"]]],
        });
    }

    operationBarHeight(operation, day, kind) {
        const ceiling = Math.max(...operation.days.map((item) => item.on_time + item.late), 1);
        return `${Math.max(4, (day[kind] / ceiling) * 100)}%`;
    }
}

registry.category("actions").add("primetech_product_stock_overview", PrimetechStockDashboard);
