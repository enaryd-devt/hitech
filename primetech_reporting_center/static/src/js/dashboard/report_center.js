/** @odoo-module **/

import { Component } from "@odoo/owl";

export class Sidebar extends Component {}

Sidebar.template =
    "primetech_reporting_center.Sidebar";

Sidebar.props = {
    collapsed: Boolean,
    onToggle: Function,
};