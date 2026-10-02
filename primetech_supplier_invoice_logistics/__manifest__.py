# -*- coding: utf-8 -*-
{
    "name": "Primetech - Facturation logistique, réceptions et livraisons",
    "summary": "Factures, coûts logistiques, réceptions, livraisons, retours et avoirs liés",
    "version": "18.0.1.1.0",
    "category": "Accounting/Inventory",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["account", "stock", "purchase", "om_account_asset"],
    "data": [
        "views/product_category_views.xml",
        "views/account_move_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "primetech_supplier_invoice_logistics/static/src/js/chatter_bottom.js",
            "primetech_supplier_invoice_logistics/static/src/js/supplier_invoice_article_tooltip.js",
            "primetech_supplier_invoice_logistics/static/src/scss/chatter_bottom.scss",
            "primetech_supplier_invoice_logistics/static/src/scss/supplier_invoice_lines.scss",
        ],
    },
    "installable": True,
    "application": False,
}
