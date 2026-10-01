/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";

// Keep the conversation area below the sheet on the two business documents
// extended by this module, including on extra-large desktop screens.
patch(FormRenderer.prototype, {
    mailLayout(hasAttachmentContainer) {
        const model = this.props.record.resModel;
        const isSupplierInvoice = model === "account.move"
            && ["in_invoice", "in_refund"].includes(this.props.record.data.move_type);
        if ((isSupplierInvoice || model === "stock.picking") && this.env.services["mail.store"]) {
            return "BOTTOM_CHATTER";
        }
        return super.mailLayout(hasAttachmentContainer);
    },
});
