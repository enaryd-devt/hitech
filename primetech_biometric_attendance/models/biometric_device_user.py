# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


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
    device_user_name = fields.Char(string='Nom sur la pointeuse', size=24,
                                   help="Nom affiché par la pointeuse (24 caractères au maximum). "
                                        "Modifiez-le puis cliquez sur « Mettre à jour la pointeuse ».")
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

    DEVICE_FIELDS = ('device_user_name', 'privilege', 'card', 'password', 'device_user_id')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.device_user_id:
            self.device_user_id = self.employee_id.device_id_num
        if self.employee_id and not self.device_user_name:
            self.device_user_name = (self.employee_id.name or '')[:24]

    @api.constrains('device_user_id', 'device_user_name', 'card', 'password')
    def _check_device_values(self):
        for record in self:
            if not (record.device_user_id or '').isdigit() or len(record.device_user_id) > 9:
                raise ValidationError(_("L'identifiant biométrique doit être un nombre de 1 à 9 chiffres (%s).",
                                        record.device_user_id))
            if record.card and not record.card.isdigit():
                raise ValidationError(_('Le numéro de carte doit être numérique.'))
            password = record.sudo().password
            if password and (not password.isdigit() or len(password) > 8):
                raise ValidationError(_('Le mot de passe de la pointeuse contient au plus 8 chiffres.'))

    def _device_name(self):
        """Name written on the device: the edited one, else the employee's."""
        self.ensure_one()
        return ((self.device_user_name or self.employee_id.name or '').strip())[:24]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('biometric_from_device'):
            for record in records.filtered(lambda user: not user.device_user_name and user.employee_id):
                record.device_user_name = (record.employee_id.name or '')[:24]
        return records

    def write(self, vals):
        from_device = self.env.context.get('biometric_from_device')
        result = super().write(vals)
        if not from_device and set(vals) & set(self.DEVICE_FIELDS):
            # Edited in Odoo: protected from the next device reading until sent.
            super().write({'sync_state': 'pending', 'sync_message': _(
                'Modifié dans Odoo : cliquez sur « Mettre à jour la pointeuse » pour l’appliquer sur l’appareil.')})
        if vals.get('employee_id') and not from_device:
            for record in self.filtered(lambda user: not user.device_user_name):
                record.device_user_name = (record.employee_id.name or '')[:24]
        if vals.get('employee_id'):
            for record in self.filtered(lambda record: not record.employee_id.device_id_num):
                record.employee_id.device_id_num = record.device_user_id
            # Punches of a newly mapped identifier are imported at the next synchronisation.
            self.device_id.filtered('active').sudo().write({'last_sync_at': False, 'relay_resend_all': True})
        return result

    def action_auto_match(self):
        """Link the selected users to an employee (same device ID or identical name)."""
        matched = 0
        for record in self.filtered(lambda user: not user.employee_id):
            employee = record.device_id._match_employee(record.device_user_id, record.device_user_name)
            if employee:
                record.employee_id = employee
                matched += 1
        return self._notify_list(_('%(matched)s utilisateur(s) associé(s) automatiquement, %(left)s restant(s) '
                                   'sans employé.', matched=matched,
                                   left=len(self.filtered(lambda user: not user.employee_id))))

    def action_create_employee(self):
        """Create the missing employees from the name stored on the device."""
        Employee = self.env['hr.employee']
        created = Employee
        for record in self.filtered(lambda user: not user.employee_id):
            employee = Employee.create({
                'name': (record.device_user_name or '').strip() or _('Employé pointeuse %s', record.device_user_id),
                'device_id_num': record.device_user_id,
                'company_id': record.device_id.company_id.id,
            })
            record.employee_id = employee
            created |= employee
        return self._notify_list(_('%s employé(s) créé(s). Complétez leur fiche (poste, département, horaire) '
                                   'dans Employés.', len(created)))

    def _notify_list(self, message):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'success', 'sticky': False,
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def _relay_notification(self, message):
        relay_devices = self.device_id.filtered(lambda device: device.connection_mode == 'relay')
        return relay_devices[:1]._notify(message) if relay_devices else True

    def action_push_to_device(self):
        for record in self:
            if not record._device_name():
                raise UserError(_("Indiquez le nom sur la pointeuse ou un employé pour l'identifiant %s.",
                                  record.device_user_id))
            record.device_id._push_device_user(record)
        return self._relay_notification(_(
            "Envoi transmis à la passerelle : l'utilisateur sera créé sur la pointeuse à sa "
            "prochaine synchronisation (moins d'une minute si un PC du site est allumé)."))

    def action_remove_from_device(self):
        for record in self:
            record.device_id._remove_device_user(record)
        return self._relay_notification(_(
            "Retrait transmis à la passerelle : il sera effectué à sa prochaine synchronisation."))

    @api.constrains('device_user_id')
    def _check_device_user_id(self):
        for record in self:
            if not record.device_user_id or not record.device_user_id.strip():
                raise ValidationError(_('L’identifiant biométrique est obligatoire.'))
