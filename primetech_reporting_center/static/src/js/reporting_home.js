/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class ReportingHome extends Component {
    static template = "primetech_reporting_center.ReportingHome";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ actions: [] });
        onWillStart(async () => {
            this.state.actions = await this.orm.call("primetech.reporting.home", "get_quick_actions", []);
        });
    }

    open(actionId) {
        this.action.doAction(actionId);
    }
}

registry.category("actions").add("primetech_reporting_home", ReportingHome);
