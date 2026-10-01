/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TopCustomers extends Component {

    setup() {

            this.actionService =
                useService("action");

            this.state = useState({

                loading: true,

                customers: [],

            });

        this.state = useState({

            loading: true,

            customers: [],

        });

        onWillStart(async () => {

            await this.loadCustomers();

        });

        onWillUpdateProps(async (nextProps) => {

            if (

                nextProps.refreshKey !==
                this.props.refreshKey

            ) {

                await this.loadCustomers();

            }

        });

    }

    async loadCustomers() {

        this.state.loading = true;

        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/top_customers",

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

            this.state.customers =
                data || [];

        } catch (error) {

            console.error(

                "Erreur Top Clients",

                error

            );

            this.state.customers = [];

        } finally {

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

    async openCustomer(customerId) {

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

            type: "ir.actions.act_window",

            name: "Factures Client",

            res_model: "account.move",

            views: [

                [false, "list"],

                [false, "form"],

            ],

            domain: [

                ["partner_id", "=", customerId],

                ["move_type", "=", "out_invoice"],

            ],

            target: "current",

        });

    }

}

TopCustomers.template =
    "primetech_reporting_center.TopCustomers";