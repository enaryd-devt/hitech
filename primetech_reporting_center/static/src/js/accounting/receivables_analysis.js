/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
} from "@odoo/owl";

import { rpc }
from "@web/core/network/rpc";

export class ReceivablesAnalysis extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {},

        });

        onWillStart(async () => {

            this.state.data = await rpc(

                "/primetech_reporting/accounting/receivables",

                {}

            );

            this.state.loading = false;

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

ReceivablesAnalysis.template =
    "primetech_reporting_center.ReceivablesAnalysis";