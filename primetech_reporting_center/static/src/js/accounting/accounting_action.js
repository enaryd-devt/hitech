/** @odoo-module **/

import { registry } from "@web/core/registry";
import { AccountingDashboard } from "./accounting_dashboard";

registry.category("actions").add(

    "primetech_accounting_dashboard",

        AccountingDashboard

);