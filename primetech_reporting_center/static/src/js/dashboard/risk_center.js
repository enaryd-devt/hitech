/** @odoo-module **/

import {
Component,
useState,
onWillStart,
onWillUpdateProps,
} from "@odoo/owl";

import {
useService
} from "@web/core/utils/hooks";

export class RiskCenter extends Component {


setup() {

    this.actionService =
        useService("action");

    this.state = useState({

        loading: true,

        invoices: [],

        products: [],

    });

    onWillStart(async () => {

        await this.loadData();

    });

    onWillUpdateProps(async (nextProps) => {

        if (

            nextProps.refreshKey !==
            this.props.refreshKey

        ) {

            await this.loadData();

        }

    });

}

async loadData() {

    this.state.loading = true;

    try {

        await Promise.all([

            this.loadInvoices(),

            this.loadProducts(),

        ]);

    } finally {

        this.state.loading = false;

    }

}

async loadInvoices() {

    try {

        const response = await fetch(

            "/primetech_reporting/dashboard/unpaid_invoices",

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

        this.state.invoices =
            data || [];

    } catch (error) {

        console.error(

            "Erreur factures",

            error

        );

        this.state.invoices = [];

    }

}

async loadProducts() {

    try {

        const response = await fetch(

            "/primetech_reporting/dashboard/top_reserved_products",

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

            "Erreur produits réservés",

            error

        );

        this.state.products = [];

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

async openCustomerInvoices(customerId) {

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

        name: "Factures Impayées",

        res_model: "account.move",

        views: [

            [false, "list"],

            [false, "form"],

        ],

        domain: [

            ["partner_id", "=", customerId],

            ["move_type", "=", "out_invoice"],

            ["payment_state", "in", [

                "not_paid",

                "partial",

            ]],

        ],

        target: "current",

    });

}

async openReservedProduct(productId) {

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

        name: "Produit",

        res_model: "product.product",

        res_id: productId,

        views: [

            [false, "form"]

        ],

        target: "current",

    });

}

async openDeliveryOrders(product) {

    await this.actionService.doAction({

        type: "ir.actions.act_window",

        name: "Bons de Livraison",

        res_model: "stock.picking",

        views: [

            [false, "list"],

            [false, "form"],

        ],

        domain: [

            ["id", "in", product.picking_ids]

        ],

        target: "current",

    });

}


}

RiskCenter.template =
"primetech_reporting_center.RiskCenter";
