/** @odoo-module **/

import {
Component,
useState,
onWillStart,
onWillUpdateProps,
} from "@odoo/owl";

import { useService } from "@web/core/utils/hooks";

export class TopProducts extends Component {

    setup() {

        this.actionService =
            useService("action");

        this.state = useState({

            loading: true,
            refreshing: false,

            products: [],

        });

        onWillStart(async () => {

            await this.loadProducts();

        });

        onWillUpdateProps(async (nextProps) => {

            if (

                nextProps.refreshKey !==
                this.props.refreshKey

            ) {

                await this.loadProducts();

            }

        });

    }

    async loadProducts() {

        this.state.loading = true;

        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/top_products",

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

            this.state.products =
                data || [];

        } catch (error) {

            console.error(

                "Erreur Top Produits",

                error

            );

            this.state.products = [];

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

    async openProduct(productId) {

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

                name: "Historique des ventes",

                res_model: "sale.report",

                views: [

                    [false, "list"],

                    [false, "pivot"],

                    [false, "graph"],

                ],

                domain: [

                    ["product_id", "=", productId]

                ],

                target: "current",

            });

        }

    }

    TopProducts.template =
    "primetech_reporting_center.TopProducts";
