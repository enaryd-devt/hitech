/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";

export class SalesForecast extends Component {

    setup() {

        this.state = useState({

            loading: true,

            forecast: null,

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

                "/primetech_reporting/dashboard/sales_forecast",

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

            this.state.forecast =
                result.result || result;

        }

        catch (error) {

            console.error(

                "Erreur Sales Forecast",

                error

            );

        }

        finally {

            this.state.loading = false;

        }

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

SalesForecast.template =
    "primetech_reporting_center.SalesForecast";