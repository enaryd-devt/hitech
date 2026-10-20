/** @odoo-module **/

import { Component, onWillStart, useExternalListener, useRef, useState } from "@odoo/owl";
import { CashMovePopup } from "@point_of_sale/app/navbar/cash_move_popup/cash_move_popup";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Bypass the POS/IoT printer on purpose: customer-payment receipts must open
// the browser's native print dialog.
async function printCustomerReceiptInBrowser(printer, receipt, headerData) {
    receipt.cashier_name = receipt.cashier_name || "";
    const el = await printer.renderer.toHtml(CustomerCashPaymentReceipt, { receipt, headerData });
    printer.printWeb(el);
}

export class CustomerCashPaymentReceipt extends Component {
    static template = "primetech_pos_customer_cash_payment.CustomerCashPaymentReceipt";
    static props = { receipt: Object, headerData: Object };
    formatAccountBalance(value) {
        // Receipts show an amount due, never the signed accounting balance.
        // This applies equally to customer receivables and supplier payables.
        return this.env.utils.formatCurrency(Math.abs(value || 0));
    }
    formatAmount(value) {
        return this.env.utils.formatCurrency(Math.abs(value || 0));
    }
}

export class PartnerBalanceReceipt extends Component {
    static template = "primetech_pos_customer_cash_payment.PartnerBalanceReceipt";
    static props = { balance: Object, headerData: Object };
    formatAmount(value) {
        return this.env.utils.formatCurrency(Math.abs(value || 0));
    }
}

export class PartnerBalancePopup extends Component {
    static template = "primetech_pos_customer_cash_payment.PartnerBalancePopup";
    static components = { Dialog };
    static props = { close: Function };
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.printer = useService("printer");
        this.state = useState({ search: "", partners: [], selectedPartner: null, balance: null, loading: false });
        this.searchPartners = this.searchPartners.bind(this);
        this.selectPartner = this.selectPartner.bind(this);
        this.print = this.print.bind(this);
        onWillStart(() => this.searchPartners());
    }
    async searchPartners() {
        this.state.loading = true;
        const result = await this.orm.call("pos.session", "pos_customer_payment_partners", [
            this.pos.session.id, this.state.search, 0, 30,
        ]);
        this.state.partners = result.partners;
        this.state.loading = false;
    }
    onSearchInput(event) {
        this.state.search = event.target.value;
        window.clearTimeout(this.searchTimer);
        this.searchTimer = window.setTimeout(() => this.searchPartners(), 180);
    }
    async selectPartner(partner) {
        this.state.selectedPartner = partner;
        this.state.loading = true;
        this.state.balance = await this.orm.call("pos.session", "pos_partner_global_balance", [
            this.pos.session.id, partner.id,
        ]);
        this.state.loading = false;
    }
    async print() {
        if (!this.state.balance) return;
        const el = await this.printer.renderer.toHtml(PartnerBalanceReceipt, {
            balance: this.state.balance,
            headerData: this.pos.getReceiptHeaderData(),
        });
        this.printer.printWeb(el);
        this.props.close();
    }
}

export class CustomerCashPaymentsScreen extends Component {
    static template = "primetech_pos_customer_cash_payment.CustomerCashPaymentsScreen";
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.printer = useService("printer");
        this.dialog = useService("dialog");
        // Template event handlers can invoke this method as a detached
        // function; bind it so the printer service remains available.
        this.print = this.print.bind(this);
        this.state = useState({ payments: [], loading: true, page: 0, pageSize: 150, total: 0, searchTerm: "" });
        this.loadPayments = this.loadPayments.bind(this);
        this.refresh = this.refresh.bind(this);
        this.changePage = this.changePage.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.openPartnerBalanceWizard = this.openPartnerBalanceWizard.bind(this);
        this.loadSequence = 0;
        onWillStart(() => this.loadPayments());
    }
    get totalPages() {
        return Math.max(1, Math.ceil(this.state.total / this.state.pageSize));
    }
    async loadPayments() {
        const sequence = ++this.loadSequence;
        this.state.loading = true;
        const result = await this.orm.call("pos.session", "pos_customer_payment_list", [
            this.pos.session.id,
            this.state.page * this.state.pageSize,
            this.state.pageSize,
            this.state.searchTerm,
        ]);
        if (sequence !== this.loadSequence) return;
        this.state.payments = result.payments;
        this.state.total = result.total;
        this.state.loading = false;
    }
    async changePage(direction) {
        const page = this.state.page + direction;
        if (page < 0 || page >= this.totalPages) return;
        this.state.page = page;
        await this.loadPayments();
    }
    async refresh() {
        await this.loadPayments();
    }
    onSearchInput(event) {
        this.state.searchTerm = event.target.value;
        this.state.page = 0;
        // Refresh for every inserted or deleted character without flooding
        // the server while the cashier is typing quickly.
        window.clearTimeout(this.searchTimer);
        this.searchTimer = window.setTimeout(() => this.loadPayments(), 180);
    }
    format(value) {
        return this.env.utils.formatCurrency(value || 0);
    }
    async print(payment) {
        payment.cashier_name = this.pos.get_cashier()?.name || "";
        await printCustomerReceiptInBrowser(this.printer, payment, this.pos.getReceiptHeaderData());
    }
    openPartnerBalanceWizard() {
        this.dialog.add(PartnerBalancePopup);
    }
    back() {
        this.pos.showScreen("ProductScreen");
    }
}

registry.category("pos_screens").add("CustomerCashPaymentsScreen", CustomerCashPaymentsScreen);

patch(CashMovePopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.partner_id = "";
        this.state.pos_payment_method_id = "";
        this.state.partner_type = "";
        this.partnerPaymentModes = useState({ items: [], loading: true });
        this.partnerDirectory = useState({ items: [], loading: false, search: "", open: false, offset: 0, hasMore: true });
        this.partnerSearchInput = useRef("partnerSearchInput");
        this.partnerPaymentOrm = useService("orm");
        this.onPartnerDocumentClick = this.onPartnerDocumentClick.bind(this);
        useExternalListener(document, "click", this.onPartnerDocumentClick, { capture: true });
        onWillStart(async () => {
            const items = await this.partnerPaymentOrm.call("pos.session", "pos_customer_payment_methods", [this.pos.session.id]);
            this.partnerPaymentModes.items = items;
            this.partnerPaymentModes.loading = false;
        });
    },
    get hasSelectedPartner() {
        return Boolean(Number(this.state.partner_id));
    },
    get selectedPartner() {
        const partnerId = Number(this.state.partner_id);
        return this.partnerDirectory.items.find((partner) => partner.id === partnerId);
    },
    async loadPartners(reset = false) {
        if (this.partnerDirectory.loading || (!reset && !this.partnerDirectory.hasMore)) return;
        if (reset) {
            this.partnerDirectory.items = [];
            this.partnerDirectory.offset = 0;
            this.partnerDirectory.hasMore = true;
        }
        this.partnerDirectory.loading = true;
        try {
            const result = await this.partnerPaymentOrm.call(
                "pos.session", "pos_customer_payment_partners",
                [this.pos.session.id, this.partnerDirectory.search, this.partnerDirectory.offset, 100]
            );
            this.partnerDirectory.items.push(...result.partners);
            this.partnerDirectory.offset += result.partners.length;
            this.partnerDirectory.hasMore = result.has_more;
        } finally {
            this.partnerDirectory.loading = false;
        }
    },
    async togglePartnerPicker() {
        this.partnerDirectory.open = !this.partnerDirectory.open;
        if (this.partnerDirectory.open) {
            if (!this.partnerDirectory.items.length) await this.loadPartners(true);
            // Wait for Owl to render the dropdown before focusing its input.
            requestAnimationFrame(() => this.partnerSearchInput.el?.focus());
        }
    },
    onPartnerDocumentClick(event) {
        if (!event.target.closest(".pos-customer-cash-partner-selector")) {
            this.partnerDirectory.open = false;
        }
    },
    onPartnerSearch() {
        clearTimeout(this._partnerSearchTimer);
        this._partnerSearchTimer = setTimeout(() => this.loadPartners(true), 220);
    },
    async onPartnerListScroll(ev) {
        const target = ev.currentTarget;
        if (target.scrollTop + target.clientHeight >= target.scrollHeight - 28) await this.loadPartners();
    },
    selectPartner(partner) {
        const partnerId = Number(partner.id);
        this.state.partner_id = partnerId ? String(partnerId) : "";
        // These fields only make sense for a partner accounting payment.
        // Reset them when no partner is selected, otherwise restore defaults.
        this.state.pos_payment_method_id = partnerId ? (this.partnerPaymentModes.items[0]?.id || "") : "";
        this.state.partner_type = "";
        this.partnerDirectory.open = false;
    },
    async confirm() {
        const partnerId = Number(this.state.partner_id);
        if (!partnerId) {
            return super.confirm(...arguments);
        }
        const amount = Number.parseFloat(this.state.amount);
        if (!amount || amount <= 0) {
            this.notification.add(_t("Saisissez un montant supérieur à zéro."), { type: "danger" });
            return;
        }
        const paymentMethodId = Number(this.state.pos_payment_method_id);
        if (!paymentMethodId) {
            this.notification.add(_t("Sélectionnez un mode de paiement."), { type: "danger" });
            return;
        }
        const paymentType = this.state.type === "in" ? "inbound" : "outbound";
        try {
            const receipt = await this.pos.data.call(
                "pos.session",
                "create_customer_cash_payment",
                [[this.pos.session.id], partnerId, paymentType, amount, this.state.reason.trim(), paymentMethodId, this.state.partner_type],
                {}, true
            );
            this.props.close();
            if (!receipt.manual_reconciliation) {
                this.dialog.add(ConfirmationDialog, {
                title: _t("Imprimer le reçu de paiement ?"),
                body: _t("Voulez-vous imprimer le reçu de paiement maintenant ?"),
                confirmLabel: _t("Imprimer"),
                cancelLabel: _t("Non"),
            confirm: () => printCustomerReceiptInBrowser(
                this.printer,
                { ...receipt, cashier_name: this.pos.get_cashier()?.name || "" },
                    this.pos.getReceiptHeaderData()
                ),
                });
            }
            this.notification.add(
                receipt.manual_reconciliation
                    ? _t("Paiement en attente de lettrage manuel.")
                    : _t("Paiement et lettrage enregistrés."),
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(error.message || _t("Le paiement client n'a pas pu être enregistré."), { type: "danger" });
            throw error;
        }
    },
});

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
    },
    showCustomerCashPayments() {
        this.pos.showScreen("CustomerCashPaymentsScreen");
    },
});
