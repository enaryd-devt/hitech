# -*- coding: utf-8 -*-
{
    "name": "PrimeTech Reporting Center",
    "version": "18.0.1.1.0",
    "category": "Reporting",
    "summary": "Tableaux de bord et rapports PDF/XLSX pour piloter l'entreprise",
    "description": """
PrimeTech Reporting Center
===========================================================
Centre de pilotage centralisé pour Odoo 18 :

* tableaux de bord exécutif, comptable, commercial, achats, stock et RH ;
* rapports métier avec filtres, aperçu à l'écran et exports PDF/XLSX ;
* états comptables OHADA, analyses des ventes, achats et mouvements de stock ;
* droits d'accès par domaine et profils métier ;
* paramètres de seuils de stock et de présentation des indicateurs.

Le module exploite en lecture les données des applications Odoo déjà installées.
Il n'altère pas leurs processus de saisie, de validation ou de comptabilisation.
Consultez l'onglet « Informations » pour le guide complet d'installation,
de configuration, d'utilisation, de sécurité, de mise à jour et de désinstallation.
    """,
    "author": "PrimeTech",
    "website": "https://primetech.cm",
    "license": "LGPL-3",
    "maintainer": "PrimeTech",
    "support": "https://primetech.cm",
    "images": ["static/description/banner.png"],
    "application": True,
    "installable": True,

    "depends": [
        "base",
        "base_setup",
        "web",
        "account",
        "sale",
        "sale_stock",
        "purchase",
        "purchase_stock",
        "stock",
        "point_of_sale",
        "hr",
        "hr_attendance",
        "hr_holidays",
        "report_xlsx",
    ],

    "data": [
        # =====================================================
        # SECURITY
        # =====================================================
        "security/reporting_category.xml",
        "security/reporting_groups.xml",
        "security/ir.model.access.csv",

        # =====================================================
        # DASHBOARD (global)
        # =====================================================
        "views/dashboard/dashboard_action.xml",
        "views/dashboard/dashboard_report_preview_views.xml",
        "views/dashboard/placeholder_action.xml",
        "views/dashboard/audit_event_views.xml",
        "views/settings/res_config_settings_views.xml",


        # =====================================================
        # ACCOUNTING
        # =====================================================
        # Dashboard
        "views/accounting/accounting_dashboard_action.xml",

        # Wizards
        "views/accounting/general_ledger_wizard_views.xml",
        "views/accounting/general_ledger_actions.xml",
        "views/accounting/trial_balance_wizard_views.xml",
        "views/accounting/trial_balance_action.xml",
        "views/accounting/accounting_journal_wizard_views.xml",
        "views/accounting/accounting_journal_actions.xml",
        "views/accounting/partner_balance_wizard_views.xml",
        "views/accounting/partner_balance_actions.xml",
        "views/accounting/balance_sheet_wizard_views.xml",
        "views/accounting/balance_sheet_actions.xml",
        "views/accounting/income_statement_wizard_views.xml",
        "views/accounting/income_statement_actions.xml",
        "views/accounting/invoice_analysis_report_action.xml",
        "views/accounting/invoice_analysis_report_wizard_views.xml",
        "views/accounting/cash_period_report_wizard_views.xml",
        "views/accounting/cash_period_report_action.xml",

        # Previews
        "views/accounting/report_preview_wizard_views.xml",
        "report/preview/accounting/invoice_analysis_preview.xml",
        "report/preview/accounting/cash_period_preview.xml",

        # PDF
        "report/pdf/accounting/general_ledger_report_action.xml",
        "report/pdf/accounting/general_ledger_report.xml",
        "report/pdf/accounting/invoice_analysis_report.xml",
        "report/pdf/accounting/invoice_analysis_templates.xml",
        "report/pdf/accounting/cash_period_report.xml",
        "report/pdf/accounting/cash_period_templates.xml",
        "report/pdf/dashboard/executive_cashflow_report.xml",
        "report/pdf/dashboard/executive_cashflow_templates.xml",
        "report/pdf/dashboard/executive_top_watch_report.xml",
        "report/pdf/dashboard/executive_top_watch_templates.xml",
        "report/pdf/dashboard/executive_partner_balance_report.xml",
        "report/pdf/dashboard/executive_partner_balance_templates.xml",
        "report/pdf/accounting/trial_balance_templates.xml",
        "report/pdf/accounting/trial_balance_report.xml",
        "report/pdf/accounting/accounting_journal_templates.xml",
        "report/pdf/accounting/accounting_journal_report.xml",
        "report/pdf/accounting/partner_balance_templates.xml",
        "report/pdf/accounting/partner_balance_report.xml",
        "report/pdf/accounting/balance_sheet_templates.xml",
        "report/pdf/accounting/balance_sheet_report.xml",
        "report/pdf/accounting/income_statement_templates.xml",
        "report/pdf/accounting/income_statement_report.xml",

        # XLSX
        "report/xlsx/accounting/general_ledger_xlsx.xml",
        "report/xlsx/accounting/trial_balance_xlsx.xml",
        "report/xlsx/accounting/accounting_journal_xlsx.xml",
        "report/xlsx/accounting/partner_balance_xlsx.xml",
        "report/xlsx/accounting/balance_sheet_xlsx.xml",
        "report/xlsx/accounting/income_statement_xlsx_report.xml",
        "report/xlsx/accounting/invoice_analysis_xlsx.xml",
        "report/xlsx/accounting/cash_period_xlsx.xml",

        # =====================================================
        # SALES
        # =====================================================
        # Dashboard
        "views/sales/sales_overview_views.xml",

        # Wizards
        "views/sales/sales_periodic_report_wizard_views.xml",
        "views/sales/sales_periodic_report_action.xml",
        "views/sales/sales_customer_analysis_report_wizard_views.xml",
        "views/sales/sales_customer_analysis_report_action.xml",
        "views/sales/sales_product_analysis_report_wizard_views.xml",
        "views/sales/sales_product_analysis_report_action.xml",
        "views/sales/sales_performance_report_action.xml",
        "views/sales/sales_performance_report_wizard_views.xml",
        "views/sales/sales_orders_tracking_report_action.xml",
        "views/sales/sales_orders_tracking_report_wizard_views.xml",
        "views/sales/sales_profitability_report_action.xml",
        "views/sales/sales_profitability_report_wizard_views.xml",

        # PDF
        "report/pdf/sales/sales_periodic_templates.xml",
        "report/pdf/sales/sales_periodic_report.xml",
        "report/pdf/sales/sales_customer_analysis_templates.xml",
        "report/pdf/sales/sales_customer_analysis_report.xml",
        "report/pdf/sales/sales_product_analysis_templates.xml",
        "report/pdf/sales/sales_product_analysis_report.xml",
        "report/pdf/sales/sales_performance_templates.xml",
        "report/pdf/sales/sales_performance_report.xml",
        "report/pdf/sales/sales_orders_tracking_report.xml",
        "report/pdf/sales/sales_orders_tracking_templates.xml",
        "report/pdf/sales/sales_profitability_report.xml",
        "report/pdf/sales/sales_profitability_templates.xml",

        # Preview
        "report/preview/sales/sales_customer_analysis_preview.xml",
        "report/preview/sales/report_sales_preview_wizard_views.xml",
        "report/preview/sales/sales_product_analysis_preview.xml",
        "report/preview/sales/sales_performance_preview.xml",
        "report/preview/sales/sales_orders_tracking_preview.xml",
        "report/preview/sales/sales_profitability_preview.xml",

        # XLSX
        "report/xlsx/sales/sales_periodic_xlsx.xml",
        "report/xlsx/sales/sales_customer_analysis_xlsx.xml",
        "report/xlsx/sales/sales_product_analysis_xlsx.xml",
        "report/xlsx/sales/sales_performance_xlsx.xml",
        "report/xlsx/sales/sales_orders_tracking_xlsx.xml",
        "report/xlsx/sales/sales_profitability_xlsx.xml",

        # =====================================================
        # PURCHASE
        # =====================================================
        # Dashboard
        "views/purchase/purchase_overview_action.xml",

        # Wizards
        "views/purchase/purchase_analysis_report_action.xml",
        "views/purchase/purchase_analysis_report_wizard_views.xml",
        "views/purchase/purchase_supplier_report_action.xml",
        "views/purchase/purchase_supplier_report_wizard_views.xml",
        "views/purchase/purchase_product_report_action.xml",
        "views/purchase/purchase_product_report_wizard_views.xml",
        "views/purchase/purchase_expense_analysis_report_action.xml",
        "views/purchase/purchase_expense_analysis_report_wizard_views.xml",
        "views/purchase/purchase_order_report_wizard_views.xml",
        "views/purchase/purchase_order_report_action.xml",
        "views/purchase/purchase_receipt_report_wizard_views.xml",
        "views/purchase/purchase_receipt_report_action.xml",
        "views/purchase/purchase_bill_report_wizard_views.xml",
        "views/purchase/purchase_bill_report_action.xml",
        "views/purchase/purchase_supplier_perf_report_wizard_views.xml",
        "views/purchase/purchase_supplier_perf_report_action.xml",
        "views/purchase/purchase_lead_report_wizard_views.xml",
        "views/purchase/purchase_lead_report_action.xml",

        # PDF
        "report/pdf/purchase/purchase_analysis_templates.xml",
        "report/pdf/purchase/purchase_analysis_report.xml",
        "report/pdf/purchase/purchase_supplier_templates.xml",
        "report/pdf/purchase/purchase_supplier_report.xml",
        "report/pdf/purchase/purchase_product_templates.xml",
        "report/pdf/purchase/purchase_product_report.xml",
        "report/pdf/purchase/purchase_expense_analysis_templates.xml",
        "report/pdf/purchase/purchase_expense_analysis_report.xml",
        "report/pdf/purchase/purchase_order_report.xml",
        "report/pdf/purchase/purchase_order_templates.xml",
        "report/pdf/purchase/purchase_receipt_report.xml",
        "report/pdf/purchase/purchase_receipt_templates.xml",
        "report/pdf/purchase/purchase_bill_report.xml",
        "report/pdf/purchase/purchase_bill_templates.xml",
        "report/pdf/purchase/purchase_supplier_perf_report.xml",
        "report/pdf/purchase/purchase_supplier_perf_templates.xml",
        "report/pdf/purchase/purchase_lead_report.xml",
        "report/pdf/purchase/purchase_lead_templates.xml",

        # Preview
        "report/preview/purchase/purchase_analysis_preview.xml",
        "report/preview/purchase/report_purchase_preview_wizard_views.xml",
        "report/preview/purchase/purchase_supplier_preview.xml",
        "report/preview/purchase/purchase_product_preview.xml",
        "report/preview/purchase/purchase_expense_analysis_preview.xml",
        "report/preview/purchase/purchase_receipt_preview.xml",
        "report/preview/purchase/purchase_order_preview.xml",
        "report/preview/purchase/purchase_bill_preview.xml",
        "report/preview/purchase/purchase_supplier_perf_preview.xml",
        "report/preview/purchase/purchase_lead_preview.xml",

        # XLSX
        "report/xlsx/purchase/purchase_analysis_xlsx.xml",
        "report/xlsx/purchase/purchase_supplier_xlsx.xml",
        "report/xlsx/purchase/purchase_product_xlsx.xml",
        "report/xlsx/purchase/purchase_expense_analysis_xlsx.xml",
        "report/xlsx/purchase/purchase_order_xlsx.xml",
        "report/xlsx/purchase/purchase_receipt_xlsx.xml",
        "report/xlsx/purchase/purchase_bill_xlsx.xml",
        "report/xlsx/purchase/purchase_supplier_perf_xlsx.xml",
        "report/xlsx/purchase/purchase_lead_xlsx.xml",

        # =====================================================
        # STOCK
        # =====================================================
        # Dashboard
        "views/stock/stock_dashboard_template.xml",
        "views/stock/stock_dashboard_action.xml",
        "views/logistics/logistics_command_center_action.xml",

        # HR
        "views/hr/hr_dashboard_action.xml",
        "views/hr/hr_report_wizard_views.xml",
        "report/pdf/hr/hr_report_templates.xml",
        "report/xlsx/hr/hr_report_xlsx.xml",

        # Wizards
        "views/stock/stock_status_wizard_views.xml",
        "views/stock/stock_status_action.xml",
        "views/stock/stock_card_action.xml",
        "views/stock/stock_card_wizard_views.xml",
        "views/stock/stock_valuation_action.xml",
        "views/stock/stock_valuation_wizard_views.xml",
        "views/stock/stock_movement_action.xml",
        "views/stock/stock_movement_wizard_views.xml",
        "views/stock/stock_inventory_action.xml",
        "views/stock/stock_inventory_wizard_views.xml",

        # Preview
        "report/preview/stock/stock_status_preview.xml",
        "report/preview/stock/stock_card_preview.xml",
        "report/preview/stock/stock_valuation_preview.xml",
        "report/preview/stock/stock_inventory_preview.xml",
        "report/preview/stock/stock_movement_preview.xml",

        # PDF
        "report/pdf/stock/stock_status_report.xml",
        "report/pdf/stock/stock_status_templates.xml",
        "report/pdf/stock/stock_card_report.xml",
        "report/pdf/stock/stock_card_pdf_template.xml",
        "report/pdf/stock/stock_valuation_report.xml",
        "report/pdf/stock/stock_valuation_pdf_template.xml",
        "report/pdf/stock/stock_inventory_report.xml",
        "report/pdf/stock/stock_inventory_pdf_template.xml",
        "report/pdf/stock/stock_movement_report.xml",
        "report/pdf/stock/stock_movement_pdf_template.xml",

        # XLSX
        "report/xlsx/stock/stock_status_xlsx.xml",
        "report/xlsx/stock/stock_card_xlsx.xml",
        "report/xlsx/stock/stock_valuation_xlsx.xml",
        "report/xlsx/stock/stock_inventory_xlsx.xml",
        "report/xlsx/stock/stock_movement_xlsx.xml",

        # =====================================================
        # MENU
        # =====================================================
        "views/menu/reporting_menu.xml",
        "views/menu/dashboard_menu.xml",
        "views/menu/accounting_menu.xml",
        "views/menu/sales_menu.xml",
        "views/menu/purchase_menu.xml",
        "views/menu/stock_menu.xml",
        "views/menu/hr_menu.xml",
        # "views/menu/printing_menu.xml",
        # "views/menu/configuration_menu.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "primetech_reporting_center/static/lib/chartjs/chart.umd.js",
            "primetech_reporting_center/static/src/js/**/*.js",
            "primetech_reporting_center/static/src/xml/**/*.xml",
            "primetech_reporting_center/static/src/scss/*.scss",
        ],
        "point_of_sale._assets_pos": [
            "primetech_reporting_center/static/src/pos/pos_receipt_audit.js",
        ],
    },
}
