/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";

import { useService } from "@web/core/utils/hooks";

export class Champions extends Component {

    setup() {

        this.actionService =
            useService("action");

        this.state = useState({

            loading: true,

            customer: null,

            product: null,

            salesperson: null,

        });

        onWillStart(async () => {

            await this.loadData();

        });

        onWillUpdateProps(async () => {

            await this.loadData();

        });

    }

    async loadData() {

        this.state.loading = true;

        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/champions",

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

            if (!response.ok) {

                const error =
                    await response.text();

                console.error(

                    "Erreur Champions",

                    error

                );

                return;

            }

            const responseData =
                await response.json();

            console.log(
                "CHAMPIONS DATA",
                responseData
            );

            const data =
                responseData.result || {};

            Object.assign(

                this.state,

                {

                    customer:
                        data.customer || null,

                    product:
                        data.product || null,

                    salesperson:
                        data.salesperson || null,

                }

            );

        } catch (error) {

            console.error(

                "Erreur chargement Champions",

                error

            );

        } finally {

            this.state.loading = false;

        }

    }

    async openCustomer() {

        if (
            !this.state.customer ||
            !this.state.customer.id
        ) {
            return;
        }
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

        await this.actionService.doAction({

            type:
                "ir.actions.act_window",

            name:
                `Performance Client - ${this.state.customer.name}`,

            res_model:
                "sale.report",

            views: [

                [false, "pivot"],

                [false, "graph"],

                [false, "list"],

            ],

            domain: [

                [
                    "partner_id",
                    "=",
                    this.state.customer.id
                ],

            ],

            target:
                "current",

        });

    }

    async openProduct() {

        if (
            !this.state.product ||
            !this.state.product.id
        ) {
            return;
        }
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

        await this.actionService.doAction({

            type:
                "ir.actions.act_window",

            name:
                `Performance Produit - ${this.state.product.name}`,

            res_model:
                "sale.report",

            views: [

                [false, "pivot"],

                [false, "graph"],

                [false, "list"],

            ],

            domain: [

                [
                    "product_id",
                    "=",
                    this.state.product.id
                ],

            ],

            context: {

                search_default_groupby_partner_id: 1,

            },

            target:
                "current",

        });

    }

    async openSalesperson() {

        if (
            !this.state.salesperson ||
            !this.state.salesperson.id
        ) {
            return;
        }

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

        await this.actionService.doAction({

            type:
                "ir.actions.act_window",

            name:
                `Performance Commercial - ${this.state.salesperson.name}`,

            res_model:
                "sale.report",

            views: [

                [false, "pivot"],

                [false, "graph"],

                [false, "list"],

            ],

            domain: [

                [
                    "user_id",
                    "=",
                    this.state.salesperson.id
                ],

            ],

            context: {

                search_default_groupby_partner_id: 1,

            },

            target:
                "current",

        });

    }

    formatCurrency(amount) {

        return (

            new Intl.NumberFormat(

                "fr-FR"

            ).format(

                amount || 0

            )

            + " FCFA"

        );

    }

}

Champions.template =
    "primetech_reporting_center.Champions";