/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
} from "@odoo/owl";

import { rpc }
from "@web/core/network/rpc";

export class FinancialPosition extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {

                assets: 0,

                liabilities: 0,

                equity: 0,

                liquidity_ratio: 0,

                debt_ratio: 0,

                level: "-",

            },

        });

        onWillStart(async () => {

            await this.loadData();

        });

    }

    async loadData() {

        try {

            const data = await rpc(

                "/primetech_reporting/accounting/financial_position",

                {}

            );

            console.log(
                "FINANCIAL POSITION",
                data
            );

            this.state.data = data;

        } catch (error) {

            console.error(

                "Erreur Situation Financière",

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

FinancialPosition.template =
    "primetech_reporting_center.FinancialPosition";