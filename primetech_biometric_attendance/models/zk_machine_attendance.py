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
from collections import defaultdict

import pytz

from odoo import api, fields, models

PUNCH_TYPES = [
    ('0', 'Entrée'), ('1', 'Sortie'), ('2', 'Début de pause'), ('3', 'Retour de pause'),
    ('4', 'Entrée heures supplémentaires'), ('5', 'Sortie heures supplémentaires'),
    ('255', 'Non précisé'),
]
VERIFY_METHODS = [
    ('0', 'Mot de passe'), ('1', 'Empreinte'), ('15', 'Visage'), ('2', 'Carte'), ('3', 'Mot de passe'),
    ('4', 'Carte'), ('255', 'Non précisé'),
]
PUNCH_ROLES = [
    ('in', 'Arrivée'), ('out', 'Départ'), ('intermediate', 'Intermédiaire'),
    ('duplicate', 'Doublon ignoré'), ('outside', 'Hors période'), ('unauthorized', 'Méthode non autorisée'),
]


class ZkMachineAttendance(models.Model):
    """Raw punch read from a biometric device (or entered by HR)."""
    _name = 'zk.machine.attendance'
    _description = 'Pointage biométrique'
    _order = 'punching_time desc, id desc'
    _rec_name = 'punching_time'
    _sql_constraints = [
        ('device_punch_unique', 'unique(device_id, device_id_num, punching_time)',
         'Ce pointage a déjà été importé depuis cette pointeuse.'),
    ]

    employee_id = fields.Many2one('hr.employee', string='Employé', required=True,
                                  ondelete='cascade', index=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True,
                                    string='Département')
    company_id = fields.Many2one(related='employee_id.company_id', store=True,
                                 string='Société')
    device_id = fields.Many2one('biometric.device.details', string='Pointeuse',
                                index=True, ondelete='set null')
    device_id_num = fields.Char(string='Identifiant biométrique',
                                help="Identifiant de l'employé sur la pointeuse")
    punch_type = fields.Selection(PUNCH_TYPES, string='Type de pointage',
                                  help='Sens du pointage envoyé par la pointeuse')
    attendance_type = fields.Selection(VERIFY_METHODS, string='Méthode de pointage',
                                       help="Méthode de vérification utilisée")
    method_allowed = fields.Boolean(string='Méthode autorisée', default=True, readonly=True,
                                    help='Décidé selon les méthodes autorisées pour cet utilisateur.')
    punching_time = fields.Datetime(string='Date et heure de pointage', required=True,
                                    index=True,
                                    help="Date et heure enregistrées sur la pointeuse")
    address_id = fields.Many2one('res.partner', string='Site de travail',
                                 help="Site de travail de l'employé")
    source = fields.Selection([('device', 'Pointeuse'), ('manual', 'Saisie manuelle')],
                              string='Origine', default='manual', required=True)
    note = fields.Char(string='Motif')
    day_id = fields.Many2one('biometric.attendance.day', string='Journée',
                             index='btree_not_null', ondelete='set null', readonly=True)
    punch_role = fields.Selection(PUNCH_ROLES, string='Rôle dans la journée', readonly=True)

    def _employee_dates(self):
        """Map employees to the local dates touched by these punches."""
        result = defaultdict(set)
        for punch in self:
            tz = pytz.timezone(punch.employee_id._get_biometric_tz())
            local = pytz.utc.localize(punch.punching_time).astimezone(tz)
            result[punch.employee_id].add(local.date())
        return result

    def _recompute_days(self, employee_dates):
        if self.env.context.get('biometric_skip_recompute'):
            return
        self.env['biometric.attendance.day']._recompute_employee_dates(employee_dates)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_days(records._employee_dates())
        return records

    def write(self, vals):
        tracked = {'employee_id', 'punching_time', 'punch_type'} & set(vals)
        before = self._employee_dates() if tracked else {}
        result = super().write(vals)
        if tracked:
            dates = self._employee_dates()
            for employee, days in before.items():
                dates.setdefault(employee, set()).update(days)
            self._recompute_days(dates)
        return result

    def unlink(self):
        dates = self._employee_dates()
        result = super().unlink()
        self._recompute_days(dates)
        return result
