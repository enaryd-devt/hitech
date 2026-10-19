/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { OpeningControlPopup } from "@point_of_sale/app/store/opening_control_popup/opening_control_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ReceiptHeader } from "@point_of_sale/app/screens/receipt_screen/receipt/receipt_header/receipt_header";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { registry } from "@web/core/registry";

async function printMobileMoneyReceipt(printer, receipt, headerData) {
    const element = await printer.renderer.toHtml(PrimetechMobileMoneyReceipt, { receipt, headerData });
    printer.printWeb(element);
}

export class PrimetechMobileMoneyReceipt extends Component {
    static template = "primetech_pos_hitech_theme.MobileMoneyReceipt";
    static components = { ReceiptHeader };
    static props = { receipt: Object, headerData: Object };
    format(amount) { return this.env.utils.formatCurrency(amount || 0); }
}

export class PrimetechMobileMoneyTransactionScreen extends Component {
    static template = "primetech_pos_hitech_theme.MobileMoneyTransactionScreen";
    static props = {};

    setup() {
        this.pos = usePos();
        this.printer = useService("printer");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({
            search: "", provider: "all", operation: "all", dateFrom: "", dateTo: "",
            transactions: [], loading: true,
        });
        this.printTransaction = this.printTransaction.bind(this);
        this._searchTimer = null;
        onWillStart(() => this.loadTransactions());
    }

    async loadTransactions() {
        this.state.loading = true;
        try {
            this.state.transactions = await this.pos.data.call(
                "pos.session", "primetech_mobile_money_transaction_list",
                [[this.pos.session.id], {
                    search: this.state.search,
                    provider: this.state.provider,
                    operation: this.state.operation,
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                }], {}, true
            );
        } catch (error) {
            this.notification.add(error.message || _t("Impossible de charger les transactions."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.loadTransactions(), 180);
    }
    onFilterChanged() { this.loadTransactions(); }
    back() { this.pos.showScreen("ProductScreen"); }
    format(amount) { return this.env.utils.formatCurrency(amount || 0); }
    async printTransaction(transaction) {
        await printMobileMoneyReceipt(this.printer, {
            reference: transaction.reference,
            provider: transaction.provider,
            operation: transaction.operation,
            amount: Math.abs(transaction.amount),
            reason: transaction.reason || "",
            served_by: transaction.served_by || "",
            printed_by: this.pos.get_cashier()?.name || "",
            date: transaction.date_time || transaction.date || "",
        }, this.pos.getReceiptHeaderData());
    }
    printReport() {
        // Let the manager define the period, cashier, wallet and operation
        // in the dedicated report assistant before generating the PDF.
        this.action.doAction("primetech_pos_hitech_theme.action_primetech_mobile_money_report_wizard");
        return;
        const ids = this.state.transactions.map((transaction) => transaction.id);
        if (!ids.length) {
            this.notification.add(_t("Aucune transaction à imprimer."), { type: "warning" });
            return;
        }
        window.open(`/report/pdf/primetech_pos_hitech_theme.mobile_money_global/${ids.join(",")}`, "_blank");
    }
}

registry.category("pos_screens").add("PrimetechMobileMoneyTransactionScreen", PrimetechMobileMoneyTransactionScreen);

export class PrimetechMobileMoneyPopup extends Component {
    static template = "primetech_pos_hitech_theme.MobileMoneyPopup";
    static components = { Dialog };
    static props = ["close"];

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.printer = useService("printer");
        this.dialog = useService("dialog");
        this.confirm = this.confirm.bind(this);
        this.state = useState({
            paymentMethodId: false,
            operation: "withdrawal",
            amount: "",
            reason: "",
            saving: false,
            balances: { cash: false, wallets: [] },
        });
        onWillStart(async () => {
            this.state.balances = await this.pos.data.call(
                "pos.session", "primetech_mobile_money_balances", [[this.pos.session.id]], {}, true
            );
            this.state.paymentMethodId = this.state.balances.wallets[0]?.id || false;
        });
    }

    formatBalance(balance) {
        return balance === false ? _t("Non configuré") : this.env.utils.formatCurrency(balance);
    }

    async confirm() {
        const amount = Number.parseFloat(this.state.amount);
        if (!amount || amount <= 0) {
            this.notification.add(_t("Saisissez un montant supérieur à zéro."), { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            // Payments validated in the POS are accounted at session closing.
            // Synchronise them first so their amount is available for a
            // subsequent Mobile Money deposit in the same session.
            await this.pos.syncAllOrders();
            const result = await this.pos.data.call(
                "pos.session",
                "primetech_mobile_money_transfer",
                [[this.pos.session.id], this.state.paymentMethodId, this.state.operation, amount, this.state.reason.trim(), this.pos.get_cashier()?.id || false],
                {},
                true
            );
            result.printed_by = this.pos.get_cashier()?.name || "";
            this.notification.add(
                _t("Transaction %(operation)s %(provider)s de %(amount)s enregistrée. Nouveau solde %(provider)s : %(balance)s.", {
                    operation: result.operation,
                    provider: result.provider,
                    amount: this.env.utils.formatCurrency(result.amount),
                    balance: this.env.utils.formatCurrency(
                        result.balances.wallets.find((wallet) => wallet.id === this.state.paymentMethodId)?.balance || 0
                    ),
                }),
                { type: "success" }
            );
            this.props.close();
            this.dialog.add(ConfirmationDialog, {
                title: _t("Imprimer le ticket ?"),
                body: _t("Voulez-vous imprimer le ticket de cette transaction Mobile Money ?"),
                confirmLabel: _t("Imprimer"),
                cancelLabel: _t("Non"),
                confirm: () => printMobileMoneyReceipt(this.printer, result, this.pos.getReceiptHeaderData()),
            });
        } catch (error) {
            this.notification.add(
                error.message || _t("La transaction Mobile Money n'a pas pu être enregistrée."),
                { type: "danger" }
            );
            throw error;
        } finally {
            this.state.saving = false;
        }
    }
}

patch(ClosePosPopup.prototype, {
    getInitialState() {
        const state = super.getInitialState(...arguments);
        state.mobileMoneyMovesExpanded = {};
        for (const method of this.props.non_cash_payment_methods) {
            if (method.mobile_money_moves !== undefined && !state.payments[method.id]) {
                state.payments[method.id] = {
                    counted: this.env.utils.formatCurrency(method.amount, false),
                };
            }
        }
        return state;
    },
    toggleMobileMoneyMoves(paymentMethodId) {
        this.state.mobileMoneyMovesExpanded[paymentMethodId] =
            !this.state.mobileMoneyMovesExpanded[paymentMethodId];
    },
    isMobileMoneyMovesExpanded(paymentMethodId) {
        return Boolean(this.state.mobileMoneyMovesExpanded[paymentMethodId]);
    },
    async closeSession() {
        const walletCounts = {};
        for (const method of this.props.non_cash_payment_methods) {
            if (method.mobile_money_moves !== undefined && this.state.payments[method.id]) {
                walletCounts[method.id] = this.env.utils.parseValidFloat(
                    this.state.payments[method.id].counted
                );
            }
        }
        await this.pos.data.call(
            "pos.session", "primetech_save_mobile_money_closing_counts",
            [[this.pos.session.id], walletCounts], {}, true
        );
        return super.closeSession(...arguments);
    },
});

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
        this.state.mobileMoneyOpening = [];
        onWillStart(async () => {
            this.state.mobileMoneyOpening = await this.pos.data.call(
                "pos.session",
                "primetech_mobile_money_opening_data",
                [[this.pos.session.id]],
                {},
                true
            );
            for (const wallet of this.state.mobileMoneyOpening) {
                wallet.counted = this.env.utils.formatCurrency(wallet.amount, false);
            }
        });
    },
    async confirm() {
        if (!this.state.mobileMoneyOpening.every((wallet) => this.env.utils.isValidFloat(wallet.counted))) {
            this.notification.add(_t("Saisissez un montant valide pour chaque portefeuille Mobile Money."), {
                type: "danger",
            });
            return;
        }
        const walletAmounts = Object.fromEntries(
            this.state.mobileMoneyOpening.map((wallet) => [
                wallet.id, this.env.utils.parseValidFloat(wallet.counted),
            ])
        );
        await this.pos.data.call(
            "pos.session",
            "primetech_set_opening_control",
            [this.pos.session.id, this.env.utils.parseValidFloat(this.state.openingCash), this.state.notes, walletAmounts],
            {},
            true
        );
        this.pos.session.state = "opened";
        this.props.close();
    },
});

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
        this.primetechMobileMoneyDialog = useService("dialog");
        this.primetechMobileMoney = useState({ isManager: false });
        this.openPrimetechMobileMoney = this.openPrimetechMobileMoney.bind(this);
        this.openPrimetechMobileMoneyList = this.openPrimetechMobileMoneyList.bind(this);
        onWillStart(async () => {
            this.primetechMobileMoney.isManager = await user.hasGroup("point_of_sale.group_pos_manager");
        });
    },
    openPrimetechMobileMoney() {
        this.primetechMobileMoneyDialog.add(PrimetechMobileMoneyPopup);
    },
    openPrimetechMobileMoneyList() {
        this.pos.showScreen("PrimetechMobileMoneyTransactionScreen");
    },
});
