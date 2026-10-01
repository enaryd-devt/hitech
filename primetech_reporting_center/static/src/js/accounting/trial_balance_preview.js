/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
} from "@odoo/owl";

import { rpc } from "@web/core/network/rpc";

import { registry } from "@web/core/registry";


export class TrialBalancePreview extends Component {

    setup() {

        const context =
            this.props.action?.context || {};

        this.state = useState({

            loading: true,

            dateFrom:
                context.date_from || false,

            dateTo:
                context.date_to || false,

            level:
                context.level || "4",

            postedOnly:
                context.posted_only ?? true,

            data: {

                lines: [],

                totals_bilan: {

                    opening_debit: 0,
                    opening_credit: 0,

                    period_debit: 0,
                    period_credit: 0,

                    closing_debit: 0,
                    closing_credit: 0,

                },

                totals_gestion: {

                    opening_debit: 0,
                    opening_credit: 0,

                    period_debit: 0,
                    period_credit: 0,

                    closing_debit: 0,
                    closing_credit: 0,

                },

                totals_balance: {

                    opening_debit: 0,
                    opening_credit: 0,

                    period_debit: 0,
                    period_credit: 0,

                    closing_debit: 0,
                    closing_credit: 0,

                },

            },

        });

        onWillStart(
            async () => {

                await this.loadData();

            }
        );

    }

    async loadData() {

        this.state.loading = true;

        try {

            const result =
                await rpc(

                    "/primetech_reporting/accounting/trial_balance",

                    {

                        date_from:
                            this.state.dateFrom,

                        date_to:
                            this.state.dateTo,

                        level:
                            this.state.level,

                        posted_only:
                            this.state.postedOnly,

                    }

                );

            this.state.data =
                result || {

                    lines: [],

                    totals_bilan: {},

                    totals_gestion: {},

                    totals_balance: {},

                };

            console.log(
                "TRIAL BALANCE",
                result
            );

        }

        catch (error) {

            console.error(

                "Erreur Balance Générale",

                error

            );

        }

        finally {

            this.state.loading = false;

        }

    }

    formatCurrency(value) {

        return new Intl.NumberFormat(

            "fr-FR",

            {

                minimumFractionDigits: 0,

                maximumFractionDigits: 0,

            }

        ).format(

            value || 0

        );

    }

}


TrialBalancePreview.template =
    "primetech_reporting_center.TrialBalancePreview";


registry
    .category("actions")
    .add(

        "primetech_trial_balance",

        TrialBalancePreview

    );