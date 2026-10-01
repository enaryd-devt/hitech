{
    "name": "Primetech POS Hitech",
    "summary": "Interface Hitech moderne et ergonomique pour le Point de Vente",
    "version": "18.0.1.0.0",
    "category": "Point of Sale",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "pos_hr"],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "primetech_pos_hitech_theme/static/src/js/pos_hitech.js",
            "primetech_pos_hitech_theme/static/src/js/pos_hitech_clock.js",
            "primetech_pos_hitech_theme/static/src/xml/pos_hitech_templates.xml",
            "primetech_pos_hitech_theme/static/src/scss/pos_hitech.scss",
        ],
    },
    "installable": True,
    "application": False,
}
