/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onWillUpdateProps,
} from "@odoo/owl";

export class TargetsProgress extends Component {

    setup() {

        this.state = useState({

            loading: true,

            data: {},

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

            const response =
                await fetch(

                    "/primetech_reporting/dashboard/targets_progress",

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

            this.state.data =
                result.result;

        }

        finally {

            this.state.loading =
                false;

        }

    }

}

TargetsProgress.template =
    "primetech_reporting_center.TargetsProgress";