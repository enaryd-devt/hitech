# -*- coding: utf-8 -*-
{
    "name": "Primetech - Tableau de stock des articles",
    "summary": "Cartes Kanban de stock, seuils d'alerte et quantités optimales",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["product", "stock"],
    "data": [
        "views/product_stock_dashboard_views.xml",
        "views/stock_dashboard_menu.xml",
        "views/stock_native_overview.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "primetech_product_stock_dashboard/static/src/js/stock_dashboard.js",
            "primetech_product_stock_dashboard/static/src/xml/stock_dashboard.xml",
            "primetech_product_stock_dashboard/static/src/scss/product_stock_dashboard.scss",
        ],
    },
    "installable": True,
    "application": False,
}
