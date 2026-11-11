# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BiometricDeviceUser(models.Model):
    """Mapping between an Odoo employee and a user stored on a device."""

    _name = 'biometric.device.user'
    _description = 'Utilisateur de pointeuse biométrique'
    _order = 'device_id, device_user_id'
    _sql_constraints = [
        ('device_user_unique', 'unique(device_id, device_user_id)',
         "L'identifiant biométrique doit être unique sur une pointeuse."),
    ]

    active = fields.Boolean(default=True)
    device_id = fields.Many2one(
        'biometric.device.details', string='Pointeuse', required=True,
        ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé',
                                  ondelete='cascade', index=True,
                                  help="Les pointages de cet identifiant sont importés pour cet employé.")
    department_id = fields.Many2one(related='employee_id.department_id', string='Département')
    device_user_id = fields.Char(string='Identifiant biométrique', required=True,
                                 help="Identifiant utilisé par la pointeuse pour les pointages.")
    device_uid = fields.Integer(
        string='UID du terminal', readonly=True, copy=False,
        help="Attribué automatiquement par la pointeuse après la synchronisation.")
    device_user_name = fields.Char(string='Nom sur la pointeuse', readonly=True)
    privilege = fields.Selection([
        ('0', 'Utilisateur'), ('2', 'Enrôleur'), ('6', 'Gestionnaire'), ('14', 'Administrateur'),
    ], string='Rôle sur l’appareil', default='0', required=True)
    password = fields.Char(string='Mot de passe de l’appareil', copy=False,
                           groups='hr_attendance.group_hr_attendance_manager')
    card = fields.Char(string='Numéro de carte')
    last_synced_at = fields.Datetime(string='Dernière synchronisation avec l’appareil', readonly=True)
    sync_state = fields.Selection([
        ('pending', 'À synchroniser'), ('synced', 'Synchronisé'), ('error', 'Erreur'),
    ], string='État', default='pending', readonly=True)
    sync_message = fields.Char(string='Détails de synchronisation', readonly=True)

    @api.depends('employee_id', 'device_user_name', 'device_user_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.employee_id.name or record.device_user_name or _(
                'Identifiant %s', record.device_user_id or '?')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.device_user_id:
            self.device_user_id = self.employee_id.device_id_num

    def write(self, vals):
        result = super().write(vals)
        if vals.get('employee_id'):
            for record in self.filtered(lambda record: not record.employee_id.device_id_num):
                record.employee_id.device_id_num = record.device_user_id
            # Punches of a newly mapped identifier are imported at the next synchronisation.
            self.device_id.filtered('active').sudo().write({'last_sync_at': False, 'relay_resend_all': True})
        return result

    def action_push_to_device(self):
        for record in self:
            record.device_id._push_device_user(record)
        return True

    def action_remove_from_device(self):
        for record in self:
            record.device_id._remove_device_user(record)
        return True

    @api.constrains('device_user_id')
    def _check_device_user_id(self):
        for record in self:
            if not record.device_user_id or not record.device_user_id.strip():
                raise ValidationError(_('L’identifiant biométrique est obligatoire.'))
