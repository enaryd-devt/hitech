# -*- coding: utf-8 -*-
from odoo import fields, models

PUNCH_MODES = [
    ('first_last', 'Premier pointage = arrivée, dernier = départ'),
    ('pairs', 'Pointages successifs par paires (entrée / sortie)'),
    ('device', 'Sens entrée / sortie envoyé par la pointeuse'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    biometric_default_schedule_id = fields.Many2one(
        'biometric.attendance.schedule', string='Horaire de pointage par défaut',
        help="Horaire appliqué aux employés sans horaire propre ni horaire de département.")
    biometric_use_resource_calendar = fields.Boolean(
        string='Utiliser les heures de travail Odoo à défaut', default=True,
        help="Sans horaire de pointage, les heures de travail de l'employé "
             "(Paramètres > Heures de travail) servent à détecter retards et absences.")
    biometric_punch_mode = fields.Selection(
        PUNCH_MODES, string='Interprétation des pointages', default='first_last',
        required=True,
        help="La plupart des pointeuses n'indiquent pas si un pointage est une "
             "entrée ou une sortie : le premier pointage du jour est alors "
             "l'arrivée et le dernier le départ.")
    biometric_min_punch_interval = fields.Integer(
        string='Intervalle minimal entre deux pointages (minutes)', default=2,
        help="Les pointages répétés dans cet intervalle sont considérés comme des doublons.")
    biometric_generate_attendance = fields.Boolean(
        string='Générer les présences Odoo', default=True,
        help="Crée et met à jour les présences du module Présences à partir des pointages.")
    biometric_log_retention_days = fields.Integer(
        string='Conservation du journal (jours)', default=90)
