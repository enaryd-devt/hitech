# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
{
    'name': 'PrimeTech - Gestion des pointages',
    'version': '18.0.4.0.0',
    'category': 'Ressources humaines',
    'summary': 'Pilotage des présences, horaires, retards, absences et administration des pointeuses ZKTeco',
    'description': """PrimeTech - Gestion des pointages
=================================
* Tableau de bord temps réel : présents, retards, absents, pointeuses.
* Horaires de pointage par employé, département ou société : heures prévues,
  pause, tolérances, périodes de pointage autorisées.
* Journées de présence : arrivée, départ, retard, départ anticipé, heures
  supplémentaires, absences, congés, jours fériés, justification RH.
* Administration des pointeuses ZKTeco : synchronisation, fuseau horaire,
  informations matérielles, utilisateurs, journal, maintenance.
* Génération des présences Odoo et rapport PDF de présence.""",
    'author': 'PrimeTech',
    'company': 'PrimeTech',
    'maintainer': 'PrimeTech',
    'website': 'https://www.primetechafrik.com',
    'depends': ['base_setup', 'hr_attendance', 'resource'],
    'external_dependencies': {
        'python': ['pyzk'], },
    'data': [
        'security/ir.model.access.csv',
        'security/biometric_security.xml',
        'data/biometric_punch_method_data.xml',
        'data/biometric_cron.xml',
        'data/biometric_analysis_cron.xml',
        'views/biometric_device_details_views.xml',
        'views/biometric_device_user_views.xml',
        'views/biometric_sync_log_views.xml',
        'views/biometric_attendance_schedule_views.xml',
        'views/zk_machine_attendance_views.xml',
        'views/biometric_attendance_day_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/biometric_attendance_recompute_wizard_views.xml',
        'wizard/biometric_attendance_report_wizard_views.xml',
        'report/biometric_attendance_report.xml',
        'report/biometric_reports_pro.xml',
        'views/biometric_device_attendance_menus.xml',
        'views/hr_attendance_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'primetech_biometric_attendance/static/src/dashboard/**/*',
        ],
    },
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
}
