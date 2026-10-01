/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SmartAlerts extends Component {

    setup() {

        this.actionService =
            useService("action");

        this.state = useState({

            loading: true,

            alerts: [],

        });

        onWillStart(async () => {

            await this.loadAlerts();

        });

        onWillUpdateProps(async () => {

            await this.loadAlerts();

        });

    }

    async loadAlerts() {

        this.state.loading = true;


        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/smart_alerts",

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

            const result =
                await response.json();

            this.state.alerts =
                result.result || [];

        }

        catch (error) {

            console.error(

                "Erreur Smart Alerts",

                error

            );

        }

        finally {

            this.state.loading = false;

        }

    }

    async openAlert(alert) {

        sessionStorage.setItem(

            "primetech_dashboard_state",

            JSON.stringify({

                filters:
                    this.state.filters,

                sidebarCollapsed:
                    this.state.sidebarCollapsed,

                scrollY:
                    window.scrollY,

            })

        );

        switch (alert.action) {

            case "overdue_invoices":

                await this.actionService.doAction({

                    type:
                        "ir.actions.act_window",

                    name:
                        "Factures échues",

                    res_model:
                        "account.move",

                    views: [

                        [false, "list"],

                        [false, "form"],

                    ],

                    domain: [

                        [
                            "move_type",
                            "=",
                            "out_invoice"
                        ],

                        [
                            "payment_state",
                            "not in",
                            [

                                "paid",

                                "in_payment"

                            ]
                        ],

                    ],

                });

                break;

            case "low_stock":

                await this.actionService.doAction({

                    type:
                        "ir.actions.act_window",

                    name:
                        "Stock critique",

                    res_model:
                        "product.product",

                    views: [

                        [false, "list"],

                        [false, "form"],

                    ],

                    domain: [

                        [
                            "qty_available",
                            "<=",
                            5
                        ],

                        [
                            "qty_available",
                            ">",
                            0
                        ],

                    ],

                });

                break;

            case "out_of_stock":

                await this.actionService.doAction({

                    type:
                        "ir.actions.act_window",

                    name:
                        "Produits en rupture",

                    res_model:
                        "product.product",

                    views: [

                        [false, "list"],

                        [false, "form"],

                    ],

                    domain: [

                        [
                            "qty_available",
                            "<=",
                            0
                        ],

                    ],

                });

                break;

        }

    }

}

SmartAlerts.template =
    "primetech_reporting_center.SmartAlerts";