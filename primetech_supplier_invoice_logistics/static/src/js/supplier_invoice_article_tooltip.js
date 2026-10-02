/** @odoo-module **/

// The fixed-width article column deliberately truncates very long names.  Add
// the browser tooltip lazily to the rendered cell so the full product label is
// always available without widening the whole logistics grid.
document.addEventListener("mouseover", (event) => {
    const cell = event.target.closest(".pt-supplier-bill-lines .o_list_table td[data-name='product_id']");
    if (!cell || cell.title) {
        return;
    }
    const label = cell.innerText?.replace(/\s+/g, " ").trim();
    if (label) {
        cell.title = label;
    }
});
