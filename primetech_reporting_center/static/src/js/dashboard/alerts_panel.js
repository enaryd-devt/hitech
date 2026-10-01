/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AlertsPanel extends Component {

    setup() {

        this.orm = useService("orm");

        this.action = useService("action");

        this.state = useState({
            alerts: [],
            expanded: null,
        });

        onWillStart(async () => {
            await this.loadAlerts();
        });
        console.log("ORM", this.orm);
    }

    toggleAlert(title) {

        this.state.expanded =
            this.state.expanded === title
                ? null
                : title;
    }

    formatCurrency(amount) {

        return new Intl.NumberFormat(
            "fr-FR",
            {
                style: "currency",
                currency: "XAF",
                minimumFractionDigits: 0,
            }
        ).format(amount || 0);
    }

    getStockClass(item) {

        if (item.level === "critical") {
            return "pt-alert-product-row pt-stock-critical";
        }

        if (item.level === "warning") {
            return "pt-alert-product-row pt-stock-warning";
        }

        return "pt-alert-product-row";
    }

    openCustomer(customerId) {

        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: customerId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openProduct(productId) {

        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
        });

    }
    getStockClass(item) {

        if (item.level === "critical") {
            return "pt-alert-product-row pt-stock-critical";
        }

        if (item.level === "warning") {
            return "pt-alert-product-row pt-stock-warning";
        }

        return "pt-alert-product-row pt-stock-low";
    }
    getInvoiceClass(item) {

        if (item.level === "critical") {
            return "pt-alert-item pt-invoice-critical";
        }

        if (item.level === "warning") {
            return "pt-alert-item pt-invoice-warning";
        }

        return "pt-alert-item pt-invoice-normal";
    }
    openInvoice(invoiceId) {

        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: invoiceId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async loadAlerts() {

        const result = await this.orm.call(
            "primetech.dashboard",
            "get_alerts",
            []
        );

        console.log("ALERTS", result);

        this.state.alerts = result;
    }
}

AlertsPanel.template =
    "primetech_reporting_center.AlertsPanel";