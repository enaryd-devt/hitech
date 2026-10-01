/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";


export class PrimetechKPICards extends Component {


setup() {

        this.actionService =
            useService("action");

        this.state = useState({

            revenue: 0,
            revenue_trend: 0,

            purchases: 0,
            purchases_trend: 0,

            receivables: 0,
            receivables_trend: 0,

            deliveries: 0,
            deliveries_trend: 0,

        });

        onWillStart(async () => {

            await this.loadKpis();


        });


        onWillUpdateProps(async (nextProps) => {

            if (

                nextProps.refreshKey !==
                this.props.refreshKey

            ) {

                await this.loadKpis();

            }

        });

}

async loadKpis() {

    try {

        console.log(
            "Loading KPI...",
            this.props.filters
        );

        const response = await fetch(
            "/primetech_reporting/dashboard/kpis",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",
                },

                body: JSON.stringify(
                    this.props.filters || {}
                ),
            }
        );

        console.log(
            "HTTP Status =",
            response.status
        );

        const data =
            await response.json();

        console.log(
            "KPI DATA =",
            data
        );

        Object.assign(
            this.state,
            data
        );

    } catch (error) {

        console.error(
            "Erreur chargement KPI :",
            error
        );

    }

}

formatCurrency(amount) {

    return (
        new Intl.NumberFormat(
            "fr-FR"
        ).format(
            amount || 0
        ) + " FCFA"
    );

}

formatTrend(value) {

    return (
        Math.abs(
            value || 0
        ).toFixed(1)
        + "%"
    );

}

getTrendClass(value) {

    return value >= 0
        ? "positive"
        : "negative";

}

    getTrendIcon(value) {

        return value >= 0
            ? "▲"
            : "▼";

    }

    getFontSize(value) {

        const len =
            String(value).length;

        if (len > 30) {
            return "11px";
        }

        if (len > 25) {
            return "13px";
        }

        if (len > 20) {
            return "15px";
        }

        if (len > 16) {
            return "18px";
        }

        if (len > 12) {
            return "22px";
        }

        return "28px";

    }
        async openRevenue() {

            await this.env.services.action.doAction({

                type: "ir.actions.act_window",

                name: "Factures Clients",

                res_model: "account.move",

                views: [
                    [false, "list"],
                    [false, "form"],
                ],

                domain: [

                    ["move_type", "=", "out_invoice"],

                    ["state", "=", "posted"],

                ],

                target: "current",

            });

        }

        async openPurchases() {

            await this.env.services.action.doAction({

                type: "ir.actions.act_window",

                name: "Commandes Fournisseurs",

                res_model: "purchase.order",

                views: [
                    [false, "list"],
                    [false, "form"],
                ],

                domain: [

                    ["state", "in", [
                        "purchase",
                        "done",
                    ]],

                ],

                target: "current",

            });

        }

        async openReceivables() {

            await this.env.services.action.doAction({

                type: "ir.actions.act_window",

                name: "Créances Clients",

                res_model: "account.move",

                views: [
                    [false, "list"],
                    [false, "form"],
                ],

                domain: [

                    ["move_type", "=", "out_invoice"],

                    ["payment_state", "in", [
                        "not_paid",
                        "partial",
                    ]],

                ],

                target: "current",

            });

        }

        async openDeliveries() {

            await this.env.services.action.doAction({

                type: "ir.actions.act_window",

                name: "Livraisons en attente",

                res_model: "stock.picking",

                views: [
                    [false, "list"],
                    [false, "form"],
                ],

                domain: [

                    ["picking_type_code", "=", "outgoing"],

                    ["state", "not in", [
                        "done",
                        "cancel",
                    ]],

                ],

                target: "current",

            });

        }


}

PrimetechKPICards.template =
"primetech_reporting_center.KPICards";
