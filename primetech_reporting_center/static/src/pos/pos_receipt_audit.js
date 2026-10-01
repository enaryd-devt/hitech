/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";

patch(ReceiptScreen.prototype, {
    async printReceipt() {
        const result = await super.printReceipt(...arguments);
        const order = this.pos.get_order();
        await rpc("/primetech/audit/pos-receipt", {
            order_id: order?.backendId || order?.id || false,
            order_name: order?.name || order?.get_name?.() || "Ticket de caisse",
        }).catch(() => false);
        return result;
    },
});
