/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onWillUnmount, useState } from "@odoo/owl";
import { Navbar } from "@point_of_sale/app/navbar/navbar";

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
        this.primetechClock = useState({ now: new Date() });
        this.primetechClockTimer = setInterval(() => {
            this.primetechClock.now = new Date();
        }, 1000);
        onWillUnmount(() => clearInterval(this.primetechClockTimer));
    },

    get hitechCurrentTime() {
        return this.primetechClock.now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
    },
});
