/** @odoo-module **/

import {Component, useState, onWillStart, } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

export class FinanceKpis extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {},

        });

        onWillStart(async () => {

            await this.loadData();

        });

    }

    async loadData() {

        try {

            this.state.data =
                await rpc(

                    "/primetech_reporting/accounting/kpis",

                    {}

                );

        }

        finally {

            this.state.loading =
                false;

        }

    }

    formatCurrency(value) {

        return (

            new Intl.NumberFormat(
                "fr-FR"
            ).format(
                value || 0
            )

            + " FCFA"

        );

    }

}

FinanceKpis.template =
    "primetech_reporting_center.FinanceKpis";