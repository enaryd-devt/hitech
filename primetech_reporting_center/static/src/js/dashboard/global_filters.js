/** @odoo-module **/

import { Component } from "@odoo/owl";

export class GlobalFilters extends Component {

    onPeriodChange(ev) {

        this.props.onFiltersChanged({

            period: ev.target.value,

        });

    }

}

GlobalFilters.template =
    "primetech_reporting_center.GlobalFilters";