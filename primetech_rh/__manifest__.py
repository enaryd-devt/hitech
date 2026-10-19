# -*- coding: utf-8 -*-
{
    'name': "PrimeTech RH",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "PrimeTech Services",
    'website': "https://primetechafrik.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Human Resources',
    'version': '18.0.1.0.0',
    'post_init_hook': 'post_init_hook',

    # any module necessary for this one to work correctly
    'depends': [
        'hr',
        'hr_contract',
        'hr_holidays',
        'hr_attendance',
        'barcodes',
        'account',
    ],

    # always loaded
    'data': [
        # Gestion des présences intégrée.
        # Moteur de paie intégré : le module est désormais autonome et ne
        # nécessite plus l'addon payroll séparé.
        'security/payroll_core/hr_payroll_security.xml',
        'security/payroll_core/ir.model.access.csv',
        'data/payroll_core/hr_payroll_sequence.xml',
        'data/payroll_core/hr_payroll_data.xml',
        'views/payroll_core/menu_root.xml',
        'wizard/payroll_core/hr_payroll_contribution_register_report_views.xml',
        'wizard/payroll_core/hr_payroll_payslips_by_employees_views.xml',
        'views/payroll_core/hr_contract_views.xml',
        'views/payroll_core/hr_payroll_structure_views.xml',
        'views/payroll_core/hr_salary_rule_category_views.xml',
        'views/payroll_core/hr_contribution_register_views.xml',
        'views/payroll_core/hr_salary_rule_views.xml',
        'views/payroll_core/hr_payslip_line_views.xml',
        'views/payroll_core/hr_payslip_views.xml',
        'views/payroll_core/hr_payslip_run_views.xml',
        'views/payroll_core/hr_employee_views.xml',
        'views/payroll_core/report_contributionregister.xml',
        'views/payroll_core/report_payslip.xml',
        'views/payroll_core/report_payslipdetails.xml',
        # Gabarit autonome du bulletin, chargé avant son action de rapport.
        'views/paie/report_payslip_layout.xml',
        'report/payroll_core/report.xml',
        'views/payroll_core/res_config_settings_views.xml',
        'wizard/payroll_core/hr_payroll_send_email.xml',
        'wizard/payroll_core/hr_payslip_change_state_view.xml',

        # Extensions PrimeTech de la paie.
        'data/echelon_category_data.xml',
        'data/hr_cron.xml',
        'data/hr_paie_data.xml',
        'data/hr_paie_grid_data.xml',
        'views/echelon_views.xml',
        'views/paie/hr_paie_exercice_views.xml',
        'views/paie/hr_payroll_views.xml',
        'views/paie/hr_contract_views.xml',
        'views/paie/hr_paie_grid_views.xml',
        'views/paie/report_payslip_template.xml',
        'views/hr_employee_views.xml',
        'wizard/hr_payroll_dipe_view.xml',
        'security/ir.model.access.csv',
        'hr_report.xml',
        'hr_menuitem.xml',
        'views/attendance_core/menu_parent.xml',
        'views/dashboard_views.xml',

    ],
    # only loaded in demonstration mode
    'demo': [],

    'assets': {
        'web.assets_backend': [
            'primetech_rh/static/src/dashboard/rh_dashboard.js',
            'primetech_rh/static/src/dashboard/rh_dashboard.xml',
            'primetech_rh/static/src/dashboard/rh_dashboard.scss',
            'primetech_rh/static/src/dashboard/rh_dashboard_leaves.scss',
            'primetech_rh/static/src/dashboard/rh_dashboard_actions.scss',
            'primetech_rh/static/src/dashboard/rh_dashboard_charts.scss',
        ],
    },

}
