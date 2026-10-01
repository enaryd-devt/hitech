/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class ExecutiveDetails extends Component {
    setup() {
        this.actionService = useService("action");
        this.state = useState({ loading: true, sections: [], focus: [] });
        onWillStart(async () => this.loadDetails());
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.refreshKey !== this.props.refreshKey) {
                await this.loadDetails();
            }
        });
    }

    async loadDetails() {
        const data = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_executive_detail_sections",
            args: [this.props.filters || {}],
            kwargs: {},
        });
        Object.assign(this.state, data, { loading: false });
    }

    openAction(actionXmlId) {
        if (actionXmlId) {
            this.actionService.doAction(actionXmlId);
        }
    }

    formatMetric(metric) {
        const value = metric.value || 0;
        if (metric.format === "currency") {
            return `${new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(value)} FCFA`;
        }
        return new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
    }
}

ExecutiveDetails.template = "primetech_reporting_center.ExecutiveDetails";
