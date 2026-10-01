/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class ReportPlaceholder extends Component {}

ReportPlaceholder.template =
    "primetech_reporting_center.ReportPlaceholder";

registry.category("actions").add(
    "primetech_reporting_placeholder",
    ReportPlaceholder
);