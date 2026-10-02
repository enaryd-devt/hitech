/** @odoo-module **/

// The logistics grid uses fixed-width columns. Keep a single source of truth
// for the business labels used in its column headings and browser tooltips.
const COLUMN_LABELS = {
    primetech_product_image: "Image",
    product_id: "Article",
    name: "Libellé",
    asset_category_id: "Catégorie d’actif",
    account_id: "Compte comptable",
    analytic_distribution: "Analytique",
    quantity: "Quantité",
    primetech_stock_quantity: "Stock actuel",
    product_uom_id: "Unité de mesure",
    primetech_last_price: "Dernier prix fournisseur",
    price_unit: "Prix fournisseur",
    primetech_last_real_price: "Dernier prix réel",
    primetech_real_price: "Prix réel",
    primetech_weight_cost: "Constante de poids",
    primetech_volume_cost: "Constante de volume",
    primetech_cost_by_weight: "Coût de revient par poids",
    primetech_cost_by_volume: "Coût de revient par volume",
    primetech_last_final_purchase_cost: "Dernier coût d’achat final",
    primetech_final_cost: "Coût de revient final",
    primetech_sale_price_by_weight: "Prix de vente par poids",
    primetech_sale_price_by_volume: "Prix de vente par volume",
    primetech_last_final_sale_price: "Dernier prix de vente final",
    primetech_final_sale_price: "Prix de vente final",
    primetech_weight: "Poids",
    primetech_volume: "Volume",
    primetech_constant_cost: "Constante",
    discount: "Remise (%)",
    tax_ids: "Taxes",
    purchase_line_id: "Bon de commande fournisseur",
    purchase_order_id: "Bon de commande fournisseur",
    price_subtotal: "Total",
};

// Add native browser tooltips to all header cells, keeping every complete
// label readable even when its column is narrower than the heading itself.
document.addEventListener("mouseover", (event) => {
    const cell = event.target.closest(".pt-supplier-bill-lines .o_list_table td[data-name='product_id']");
    const header = event.target.closest(".pt-supplier-bill-lines .o_list_table th[data-name]");
    if (cell && !cell.title) {
        const label = cell.innerText?.replace(/\s+/g, " ").trim();
        if (label) {
            cell.title = label;
        }
    }
    if (header) {
        const fieldName = header.dataset.name;
        const label = COLUMN_LABELS[fieldName]
            || header.innerText?.replace(/\s+/g, " ").trim();
        if (label) {
            // Replace a possible native Odoo tooltip (CR, PV, Const., etc.)
            // with the full functional wording from COLUMN_LABELS.
            header.title = label;
        }
    }
});
