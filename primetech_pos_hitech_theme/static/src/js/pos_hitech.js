/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ProductCard } from "@point_of_sale/app/generic_components/product_card/product_card";
import { CategorySelector } from "@point_of_sale/app/generic_components/category_selector/category_selector";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";

const availableQuantity = (pos, product) => {
    if (!product?.is_storable || typeof product.qty_available !== "number") {
        return Infinity;
    }
    const reserved = (pos.get_open_orders() || [])
        .flatMap((order) => order.lines || [])
        .filter((line) => line.product_id?.id === product.id)
        .reduce((total, line) => total + line.qty, 0);
    return Math.max(0, product.qty_available - reserved);
};

const outOfStock = (pos, product, quantity = 1) =>
    product?.is_storable && availableQuantity(pos, product) < quantity;

patch(PosStore.prototype, {
    async primetechAssignOrderReference(order) {
        const prefix = `${this.config.primetech_order_reference_prefix || "COM"}`.trim();
        const padding = Number(this.config.primetech_order_sequence_padding || 4);
        const escapedPrefix = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const referencePattern = new RegExp(`^${escapedPrefix}\\d{6}\\d{${padding}}$`);
        if (!order || referencePattern.test(order.pos_reference || "")) {
            return;
        }
        const reference = await this.data
            .silentCall("pos.order", "primetech_next_reference", [this.config.id])
            .catch(() => false);
        if (reference) {
            order.update({ pos_reference: reference, name: reference });
        }
    },

    async primetechRefreshProductsAvailability(productIds) {
        const uniqueIds = [...new Set(productIds.filter(Boolean))];
        await Promise.all(
            uniqueIds.map(async (productId) => {
                const product = this.models["product.product"].get(productId);
                // Les services et consommables ne sont pas soumis au suivi
                // d'inventaire du point de vente.
                if (!product?.is_storable) {
                    return;
                }
                const availability = await this.data
                    .silentCall(
                        "product.product",
                        "primetech_pos_available_stock",
                        [productId, this.config.id, false]
                    )
                    .catch(() => false);
                if (product && availability && availability.available_quantity !== false) {
                    product.update({ qty_available: availability.available_quantity });
                }
            })
        );
    },

    async primetechReloadProductCatalog() {
        if (this._primetechReloadingProductCatalog) {
            return 0;
        }
        this._primetechReloadingProductCatalog = true;
        try {
            const products = await this.data.call(
                "product.product",
                "primetech_pos_reload_catalog",
                [this.config.id]
            );
            const data = await this.data.missingRecursive({ "product.product": products || [] });
            this.models.loadData(data);
            return (products || []).length;
        } finally {
            this._primetechReloadingProductCatalog = false;
        }
    },

    async primetechAuthorizeCurrentOrder(operation) {
        const order = this.get_order();
        if (!order) {
            return false;
        }
        if (order.uiState.primetechAuthorizationGranted) {
            return true;
        }
        const cashierId = this.get_cashier()?.id;
        const authorizedEmployeeIds = (this.config.primetech_authorized_employee_ids || []).map(
            (employee) => employee.id || employee
        );
        if (cashierId && authorizedEmployeeIds.includes(cashierId)) {
            return true;
        }
        const expectedCode = this.config.primetech_authorization_code;
        if (!expectedCode) {
            this.env.services.notification.add(
                "Aucun code d'autorisation n'est configuré. Contactez le responsable du point de vente.",
                { type: "warning" }
            );
            return false;
        }
        this.env.services.notification.add(
            `Autorisation requise pour ${operation}. Saisissez le code ou demandez au responsable.`,
            { type: "warning" }
        );
        const enteredCode = await makeAwaitable(this.dialog, TextInputPopup, {
            title: `Autorisation requise : ${operation}`,
            placeholder: "Saisissez le code d'autorisation",
        });
        if (`${enteredCode || ""}` !== `${expectedCode}`) {
            this.env.services.notification.add("Code d'autorisation invalide.", { type: "danger" });
            return false;
        }
        order.uiState.primetechAuthorizationGranted = true;
        this.env.services.notification.add("Autorisation accordée pour cette commande.", { type: "success" });
        return true;
    },

    async setup() {
        await super.setup(...arguments);
        this.primetechAssignOrderReference(this.get_order());
        this._primetechReservationSync = async (event) => {
            const order = event.detail?.order;
            if (order && !order.finalized) {
                await this.syncAllOrders({ orders: [order] }).catch(() => {});
                if (event.detail?.line?.product_id?.is_storable) {
                    await this._primetechRefreshLineStock(event.detail.line);
                }
            }
        };
        window.addEventListener("primetech-pos-reservation-changed", this._primetechReservationSync);
    },

    add_new_order(data = {}) {
        const order = super.add_new_order(...arguments);
        this.primetechAssignOrderReference(order);
        return order;
    },

    async addLineToCurrentOrder(vals) {
        const product =
            typeof vals.product_id === "number"
                ? this.data.models["product.product"].get(vals.product_id)
                : vals.product_id;
        const order = this.get_order();
        if (product?.type === "service" && order) {
            const existingLine = (order.lines || []).find(
                (line) => line.product_id?.id === product.id && line.get_quantity() > 0
            );
            if (existingLine) {
                order.select_orderline(existingLine);
                this.env.services.notification.add(
                    "Ce service est déjà présent dans la commande et reste limité à une unité.",
                    { type: "warning" }
                );
                return existingLine;
            }
            vals = { ...vals, qty: 1 };
        }
        if (outOfStock(this, product, vals.qty || 1)) {
            this.env.services.notification.add(
                "Cet article est en rupture de stock et ne peut pas être vendu.",
                { type: "danger" }
            );
            return false;
        }
        const line = await super.addLineToCurrentOrder(...arguments);
        if (line) {
            window.dispatchEvent(
                new CustomEvent("primetech-pos-reservation-changed", {
                    detail: { order: this.get_order(), line },
                })
            );
        }
        return line;
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        // Odoo creates a short-lived line before merging it into an existing
        // one. Keep track of that operation so this temporary line is not
        // treated as a second reservation by the quantity guard below.
        const product =
            typeof vals.product_id === "number"
                ? this.data.models["product.product"].get(vals.product_id)
                : vals.product_id;
        const productId = product?.id;
        if (productId) {
            order._primetechAddingProductId = productId;
        }
        try {
            return await super.addLineToOrder(...arguments);
        } finally {
            if (productId && order._primetechAddingProductId === productId) {
                delete order._primetechAddingProductId;
            }
        }
    },

    async _primetechRefreshLineStock(line) {
        const orderId = typeof line.order_id?.id === "number" ? line.order_id.id : false;
        // A brand-new order has not yet received its server id.  Its own
        // reservation must not be included in the server comparison, or its
        // quantity would be deducted a second time.
        if (!orderId) {
            return;
        }
        const availability = await this.data.silentCall(
            "product.product",
            "primetech_pos_available_stock",
            [line.product_id.id, this.config.id, orderId]
        );
        if (!availability || availability.available_quantity === false) {
            return;
        }
        const maximumQuantity = Math.max(0, availability.available_quantity);
        if (line.get_quantity() > maximumQuantity) {
            line.set_quantity(maximumQuantity);
            this.notification.add(
                `Stock mis à jour : seulement ${maximumQuantity} unité(s) sont encore disponibles pour cet article.`,
                { type: "warning" }
            );
            await this.syncAllOrders({ orders: [line.order_id] }).catch(() => {});
        }
    },
});

patch(ProductCard.prototype, {
    get availableQuantity() {
        const quantity = availableQuantity(this.env.services.pos, this.props.product);
        return Number.isFinite(quantity) ? quantity : this.props.product.qty_available;
    },
    get primetechStockLevel() {
        const quantity = this.availableQuantity;
        if (quantity <= 0 || quantity <= (this.env.services.pos.config.primetech_stock_critical_level || 0)) {
            return "critical";
        }
        if (quantity <= (this.env.services.pos.config.primetech_stock_warning_level || 0)) {
            return "warning";
        }
        return "available";
    },
});

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
        const storageKey = "primetech_pos_hitech_dark_mode";
        const darkMode = window.localStorage.getItem(storageKey) === "true";
        this.hitechThemeState = useState({ darkMode });
        this.hitechCatalogState = useState({ reloading: false });
        document.documentElement.classList.toggle("primetech-pos-dark", darkMode);
    },

    get hitechDarkMode() {
        return this.hitechThemeState.darkMode;
    },

    toggleHitechDarkMode() {
        this.hitechThemeState.darkMode = !this.hitechThemeState.darkMode;
        document.documentElement.classList.toggle(
            "primetech-pos-dark",
            this.hitechThemeState.darkMode
        );
        window.localStorage.setItem(
            "primetech_pos_hitech_dark_mode",
            `${this.hitechThemeState.darkMode}`
        );
    },

    get hitechCatalogReloading() {
        return this.hitechCatalogState.reloading;
    },

    async reloadProductCatalog() {
        if (this.hitechCatalogState.reloading) {
            return;
        }
        this.hitechCatalogState.reloading = true;
        try {
            const count = await this.pos.primetechReloadProductCatalog();
            this.notification.add(
                `${count} article(s) ont été rechargés depuis le serveur.`,
                { type: "success" }
            );
        } catch (error) {
            console.error("Impossible de recharger le catalogue du point de vente.", error);
            this.notification.add(
                "Le catalogue n'a pas pu être rechargé. Vérifiez votre connexion puis réessayez.",
                { type: "danger" }
            );
        } finally {
            this.hitechCatalogState.reloading = false;
        }
    },
});

patch(CategorySelector.prototype, {
    get primetechAllCategoriesSelected() {
        return !this.props.categories.some((category) => category.isSelected);
    },
});

patch(OrderSummary.prototype, {
    async setLinePrice(line, price) {
        const newPrice = Number(price);
        const referencePrice = line.product_id.get_price(
            line.order_id.pricelist_id,
            line.get_quantity(),
            line.get_price_extra()
        );
        if (Number.isFinite(newPrice) && newPrice < referencePrice) {
            const allowed = await this.pos.primetechAuthorizeCurrentOrder("baisse de prix");
            if (!allowed) {
                return false;
            }
        }
        return await super.setLinePrice(...arguments);
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder() {
        const soldProductIds = (this.currentOrder?.lines || []).map((line) => line.product_id?.id);
        const result = await super.validateOrder(...arguments);
        if (soldProductIds.length) {
            await this.pos.primetechRefreshProductsAvailability(soldProductIds);
        }
        return result;
    },
});

patch(PosOrderline.prototype, {
    set_quantity(quantity, keep_price) {
        const requestedQuantity =
            typeof quantity === "number" ? quantity : parseFloat(`${quantity || 0}`);
        const product = this.product_id;
        if (product?.type === "service" && requestedQuantity > 1) {
            const result = super.set_quantity(1, keep_price);
            window.dispatchEvent(
                new CustomEvent("primetech-pos-reservation-changed", {
                    detail: { order: this.order_id, line: this },
                })
            );
            return {
                title: "Service limité à une unité",
                body: "Un service ne peut être ajouté qu'une seule fois à cette commande.",
            };
        }
        if (
            product?.is_storable &&
            typeof product.qty_available === "number" &&
            requestedQuantity > 0
        ) {
            const reservedByOtherLines = (this.models["pos.order"] || [])
                .filter((order) => !order.finalized)
                .flatMap((order) => order.lines || [])
                .filter(
                    (line) =>
                        line !== this &&
                        line.product_id?.id === product.id &&
                        !(
                            this.order_id?._primetechAddingProductId === product.id &&
                            line.order_id === this.order_id
                        )
                )
                .reduce((total, line) => total + line.qty, 0);
            const maximumQuantity = Math.max(0, product.qty_available - reservedByOtherLines);
            if (requestedQuantity > maximumQuantity) {
                const result = super.set_quantity(maximumQuantity, keep_price);
                window.dispatchEvent(
                    new CustomEvent("primetech-pos-reservation-changed", {
                        detail: { order: this.order_id, line: this },
                    })
                );
                return {
                    title: "Quantité limitée par le stock",
                    body: `Vous ne pouvez vendre que ${maximumQuantity} unité(s) disponible(s) pour cet article. La quantité du panier a été ajustée.`,
                };
            }
        }
        const result = super.set_quantity(...arguments);
        window.dispatchEvent(
            new CustomEvent("primetech-pos-reservation-changed", {
                detail: { order: this.order_id, line: this },
            })
        );
        return result;
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.hitechState = useState({ sort: "recent" });
    },

    get hitechSort() {
        return this.hitechState.sort;
    },

    setHitechSort(sort) {
        this.hitechState.sort = sort;
    },

    clearHitechCart() {
        const order = this.currentOrder || this.pos.get_order();
        if (!order?.lines?.length) {
            return;
        }
        for (const line of [...order.lines]) {
            order.removeOrderline(line);
        }
        window.dispatchEvent(
            new CustomEvent("primetech-pos-reservation-changed", {
                detail: { order },
            })
        );
        this.notification.add("Le panier a été vidé.", { type: "success" });
    },

    async addProductToOrder(product) {
        if (outOfStock(this.pos, product)) {
            this.notification.add("Cet article est en rupture de stock et ne peut pas être vendu.", {
                type: "danger",
            });
            return;
        }
        return super.addProductToOrder(...arguments);
    },

    get productsToDisplay() {
        // The category store is briefly refreshed while switching category.
        // Keep the product grid renderable during that transition.
        const products = [...(super.productsToDisplay || [])];
        if (this.hitechState.sort === "name") {
            return products.sort((left, right) =>
                (left.display_name || left.name || "").localeCompare(
                    right.display_name || right.name || ""
                )
            );
        }
        if (this.hitechState.sort === "price") {
            return products.sort((left, right) =>
                this.pos.getProductPrice(right) - this.pos.getProductPrice(left)
            );
        }
        return products.sort((left, right) => right.id - left.id);
    },
});
