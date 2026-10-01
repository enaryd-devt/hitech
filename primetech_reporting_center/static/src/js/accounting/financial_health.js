/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
} from "@odoo/owl";

import { rpc }
from "@web/core/network/rpc";

export class FinancialHealth extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {},

        });

        onWillStart(async () => {

            this.state.data = await rpc(

                "/primetech_reporting/accounting/financial_health",

                {}

            );

            this.state.loading = false;

        });

    }

}

FinancialHealth.template =
    "primetech_reporting_center.FinancialHealth";