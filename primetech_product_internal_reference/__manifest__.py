# -*- coding: utf-8 -*-
{
    "name": "Primetech - Références internes produits",
    "summary": "Génération automatique des références produits depuis les catégories",
    "version": "18.0.1.0.16",
    "category": "Inventory/Inventory",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["product", "primetech_supplier_invoice_logistics"],
    "data": [
        "data/ir_sequence_data.xml",
        "views/product_template_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "primetech_product_internal_reference/static/src/js/rolling_code_field.js",
            "primetech_product_internal_reference/static/src/xml/barcode_generator_field.xml",
            "primetech_product_internal_reference/static/src/scss/product_internal_reference.scss",
        ],
    },
    "installable": True,
    "application": False,
}
