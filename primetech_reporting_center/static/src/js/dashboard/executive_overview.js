/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class ExecutiveOverview extends Component {
    setup() {
        this.actionService = useService("action");
        this.state = useState({
            loading: true,
            period: "month",
            period_label: "Ce mois",
            revenue_total: 0,
            invoice_revenue: 0,
            pos_revenue: 0,
            gross_margin: 0,
            purchase_total: 0,
            stock_value: 0,
            bank_balance: 0,
            cash_registers: { opened: 0, closed: 0, opening_balance: 0, current_balance: 0, closing_balance: 0, sessions: [] },
            stock_alerts: { out_of_stock: 0, pending_transfers: 0 },
            hr: { employees: 0, on_leave: 0 },
        });
        onWillStart(async () => this.loadOverview());
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.refreshKey !== this.props.refreshKey) {
                await this.loadOverview();
            }
        });
    }

    async loadOverview() {
        const filters = { ...(this.props.filters || {}), period: this.state.period };
        const data = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_executive_overview",
            args: [filters],
            kwargs: {},
        });
        Object.assign(this.state, data, { loading: false });
    }

    async setPeriod(period) {
        this.state.period = period;
        this.state.loading = true;
        this.props.onFiltersChanged({ period, dateFrom: null, dateTo: null });
        await this.loadOverview();
    }

    openAction(actionXmlId) {
        this.actionService.doAction(actionXmlId);
    }

    openRevenue() {
        this.openAction("primetech_reporting_center.action_sales_overview_dashboard");
    }

    openAccounting() {
        this.openAction("primetech_reporting_center.action_accounting_dashboard");
    }

    openStock() {
        this.openAction("primetech_reporting_center.action_stock_dashboard");
    }


    openHr() {
        this.openAction("primetech_reporting_center.action_hr_overview_dashboard");
    }

    formatCurrency(amount) {
        return `${new Intl.NumberFormat("fr-FR").format(Math.round(amount || 0))} FCFA`;
    }
}

ExecutiveOverview.template = "primetech_reporting_center.ExecutiveOverview";
