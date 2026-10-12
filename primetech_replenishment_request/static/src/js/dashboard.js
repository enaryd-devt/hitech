/** @odoo-module **/

import { registry } from "@web/core/registry";

registry.category("services").add("primetech_replenishment_dashboard", {
    start() {
        return { name: "primetech_replenishment_dashboard" };
    },
});
