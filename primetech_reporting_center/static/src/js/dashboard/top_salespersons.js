/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";

import { useService } from "@web/core/utils/hooks";

export class TopSalespersons extends Component {

    setup() {

        this.actionService =
            useService("action");

        this.state = useState({

            loading: true,

            salespersons: [],

        });

        onWillStart(async () => {

            await this.loadSalespersons();

        });

        onWillUpdateProps(async (nextProps) => {

            if (

                nextProps.refreshKey !==
                this.props.refreshKey

            ) {

                await this.loadSalespersons();

            }

        });

    }

    async loadSalespersons() {

        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/top_salespersons",

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

            const data =
                await response.json();

            this.state.salespersons =
                data || [];

        } catch (error) {

            console.error(

                "Erreur Top Commerciaux",

                error

            );

            this.state.salespersons = [];

        }

        finally {

            this.state.loading = false;

        }

    }

    formatCurrency(amount) {

        return (

            new Intl.NumberFormat(
                "fr-FR"
            ).format(amount)

            + " FCFA"

        );

    }

    async openSalesperson(userId) {

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
                "Commandes Commercial",

            res_model:
                "sale.order",

            views: [

                [false, "list"],

                [false, "form"],

            ],

            domain: [

                ["user_id", "=", userId],

                ["state", "in", [

                    "sale",

                    "done",

                ]],

            ],

            target: "current",

        });

    }

}

TopSalespersons.template =
    "primetech_reporting_center.TopSalespersons";