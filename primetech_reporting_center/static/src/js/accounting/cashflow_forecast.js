/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
} from "@odoo/owl";

import { rpc }
from "@web/core/network/rpc";

export class CashflowForecast extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {

                incoming: 0,

                outgoing: 0,

                projected: 0,

            },

        });

        onWillStart(async () => {

            await this.loadData();

        });

    }

    async loadData() {

        try {

            const data = await rpc(

                "/primetech_reporting/accounting/cashflow",

                {}

            );

            console.log(
                "CASHFLOW DATA",
                data
            );

            this.state.data = data;

        } catch (error) {

            console.error(

                "Erreur Cashflow",

                error

            );

        } finally {

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

CashflowForecast.template =
    "primetech_reporting_center.CashflowForecast";