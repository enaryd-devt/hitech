{
    "name": "PrimeTech - Paiements clients POS",
    "summary": "Paiements clients en espèces et reçus depuis le point de vente",
    "version": "18.0.1.0.27",
    "category": "Point of Sale",
    "author": "PrimeTech Services",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/partner_balance_receipt_wizard_views.xml",
        "views/account_payment_views.xml",
        "views/report_payment_receipt_views.xml",
        "views/pos_session_views.xml",
        "report/partner_balance_receipt_report.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "primetech_pos_customer_cash_payment/static/src/js/cash_customer_payment.js",
            "primetech_pos_customer_cash_payment/static/src/xml/cash_customer_payment.xml",
            "primetech_pos_customer_cash_payment/static/src/scss/customer_cash_payments.scss",
        ],
    },
    "installable": True,
}
