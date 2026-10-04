# -*- coding: utf-8 -*-
{
    "name": "Primetech - Facturation logistique, réceptions et livraisons",
    "summary": "Factures, coûts logistiques, réceptions, livraisons, retours et avoirs liés",
    "version": "18.0.1.1.0",
    "category": "Accounting/Inventory",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["account", "stock", "sale", "purchase", "point_of_sale", "om_account_asset"],
    "data": [
        "security/ir.model.access.csv",
        "data/primetech_invoice_sequences.xml",
        "views/product_category_views.xml",
        "views/account_move_views.xml",
        "views/stock_picking_views.xml",
        "reports/primetech_invoice_reports.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "primetech_supplier_invoice_logistics/static/src/js/chatter_bottom.js",
            "primetech_supplier_invoice_logistics/static/src/js/supplier_invoice_article_tooltip.js",
            "primetech_supplier_invoice_logistics/static/src/scss/chatter_bottom.scss",
            "primetech_supplier_invoice_logistics/static/src/scss/supplier_invoice_lines.scss",
            "primetech_supplier_invoice_logistics/static/src/scss/product_invoice_history.scss",
        ],
    },
    "installable": True,
    "application": False,
}
