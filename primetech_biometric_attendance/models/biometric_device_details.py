# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author:  Cybrosys Techno Solutions(<https://www.cybrosys.com>)
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
import logging
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
try:
    from zk import ZK
except ImportError:
    ZK = None
    _logger.error("Please Install pyzk library.")


def _default_timezone(model):
    company = model.env.company
    return (company.partner_id.tz or company.resource_calendar_id.tz or model.env.user.tz
            or 'Africa/Douala')


class BiometricDeviceDetails(models.Model):
    """Configuration, administration and synchronisation of a ZKTeco device."""
    _name = 'biometric.device.details'
    _description = 'Pointeuse biométrique'
    _order = 'name'

    name = fields.Char(string='Nom', required=True, help='Nom de la pointeuse')
    device_ip = fields.Char(string='Adresse IP', required=True,
                            help="Adresse IP de la pointeuse")
    port_number = fields.Integer(string='Numéro de port', required=True, default=4370,
                                 help="Port de communication (4370 par défaut)")
    comm_key = fields.Integer(string='Clé de communication', default=0,
                              groups='hr_attendance.group_hr_attendance_manager',
                              help="Mot de passe de communication défini sur la pointeuse "
                                   "(Menu > Communication). 0 si aucun.")
    address_id = fields.Many2one('res.partner', string='Site de travail',
                                 help='Site de travail associé à la pointeuse')
    company_id = fields.Many2one('res.company', string='Société', required=True,
                                 default=lambda self: self.env.company,
                                 help='Société active')
    active = fields.Boolean(default=True)
    timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        string='Fuseau horaire de la pointeuse', required=True,
        default=lambda self: _default_timezone(self),
        help="Fuseau horaire de l'heure affichée par la pointeuse. Les pointages "
             "sont convertis depuis ce fuseau, quel que soit l'utilisateur qui synchronise.")
    connection_mode = fields.Selection([
        ('direct', 'Connexion directe (Odoo interroge la pointeuse)'),
        ('relay', 'Passerelle locale (un PC du site envoie les pointages)'),
    ], string='Mode de connexion', default='direct', required=True,
        help="Connexion directe : le serveur Odoo doit joindre l'adresse IP de la pointeuse "
             "(même réseau ou VPN). Passerelle : un PC du site lit la pointeuse et envoie les "
             "pointages à Odoo par Internet ; les pointages faits PC éteints sont envoyés au "
             "démarrage du premier PC, avec leur heure réelle.")
    relay_token = fields.Char(string='Clé de la passerelle', copy=False,
                              groups='hr_attendance.group_hr_attendance_manager')
    relay_resend_all = fields.Boolean(string='Renvoyer toute la mémoire', copy=False,
                                      help="Demande à la passerelle de renvoyer tous les pointages "
                                           "de la pointeuse à la prochaine synchronisation.")
    relay_pending_commands = fields.Char(string='Commandes en attente', copy=False, readonly=True)
    relay_agent = fields.Char(string='Dernière passerelle', readonly=True, copy=False)
    connection_timeout = fields.Integer(string='Délai de connexion (secondes)',
                                        default=10, required=True)
    force_udp = fields.Boolean(string='Utiliser UDP',
                               help="À activer uniquement si la configuration de la pointeuse l'exige.")
    sync_interval = fields.Integer(string='Intervalle de synchronisation (minutes)',
                                   default=1, required=True)
    import_from_date = fields.Date(
        string='Importer les pointages à partir du',
        help="Les pointages plus anciens présents dans la pointeuse sont ignorés.")
    create_unknown_employee = fields.Boolean(
        string='Créer les employés inconnus',
        help="Crée automatiquement un employé pour chaque identifiant inconnu. "
             "Sinon, les pointages des identifiants inconnus sont mis en attente "
             "jusqu'à ce que l'utilisateur soit associé à un employé.")
    last_sync_at = fields.Datetime(string='Dernière synchronisation', readonly=True)
    last_contact_at = fields.Datetime(string='Dernier contact réussi', readonly=True)
    last_punch_at = fields.Datetime(string='Dernier pointage importé', readonly=True)
    last_sync_state = fields.Selection([
        ('never', 'Non synchronisé'), ('success', 'Synchronisé'),
        ('warning', 'Synchronisé avec avertissement'), ('error', 'Erreur de connexion'),
    ], string='État de synchronisation', default='never', readonly=True)
    last_sync_message = fields.Char(string='Détails de la dernière synchronisation', readonly=True)
    is_online = fields.Boolean(string='En ligne', compute='_compute_is_online')
    device_user_ids = fields.One2many('biometric.device.user', 'device_id',
                                      string='Utilisateurs de l’appareil')
    sync_log_ids = fields.One2many('biometric.sync.log', 'device_id', string='Journal')
    punch_count = fields.Integer(string='Pointages', compute='_compute_counts')
    unmapped_user_count = fields.Integer(string='Utilisateurs non associés',
                                         compute='_compute_counts')
    # Hardware information read from the device
    info_device_name = fields.Char(string='Modèle', readonly=True)
    info_serial = fields.Char(string='Numéro de série', readonly=True)
    info_firmware = fields.Char(string='Firmware', readonly=True)
    info_platform = fields.Char(string='Plateforme', readonly=True)
    info_mac = fields.Char(string='Adresse MAC', readonly=True)
    info_user_count = fields.Integer(string='Utilisateurs enregistrés', readonly=True)
    info_user_capacity = fields.Integer(string='Capacité utilisateurs', readonly=True)
    info_finger_count = fields.Integer(string='Empreintes enregistrées', readonly=True)
    info_finger_capacity = fields.Integer(string='Capacité empreintes', readonly=True)
    info_face_count = fields.Integer(string='Visages enregistrés', readonly=True)
    info_face_capacity = fields.Integer(string='Capacité visages', readonly=True)
    info_record_count = fields.Integer(string='Pointages en mémoire', readonly=True)
    info_record_capacity = fields.Integer(string='Capacité pointages', readonly=True)
    info_memory_usage = fields.Float(string='Mémoire pointages utilisée (%)',
                                     compute='_compute_memory_usage')
    info_time_drift = fields.Integer(string='Écart d’horloge (secondes)', readonly=True,
                                     help="Heure de la pointeuse moins heure du serveur "
                                          "lors de la dernière lecture.")
    info_updated_at = fields.Datetime(string='Informations lues le', readonly=True)

    _sql_constraints = [
        ('device_address_unique', 'unique(device_ip, port_number, company_id)',
         'Cette pointeuse (adresse IP et port) est déjà déclarée.'),
    ]

    def _compute_is_online(self):
        now = fields.Datetime.now()
        for device in self:
            device.is_online = bool(device.last_contact_at and (now - device.last_contact_at) <= timedelta(
                minutes=max(device.sync_interval, 1) * 3 + 2))

    def _compute_counts(self):
        punches = dict(self.env['zk.machine.attendance']._read_group(
            [('device_id', 'in', self.ids)], ['device_id'], ['__count']))
        unmapped = dict(self.env['biometric.device.user']._read_group(
            [('device_id', 'in', self.ids), ('employee_id', '=', False)],
            ['device_id'], ['__count']))
        for device in self:
            device.punch_count = punches.get(device, 0)
            device.unmapped_user_count = unmapped.get(device, 0)

    @api.depends('info_record_count', 'info_record_capacity')
    def _compute_memory_usage(self):
        for device in self:
            device.info_memory_usage = (
                100.0 * device.info_record_count / device.info_record_capacity
                if device.info_record_capacity else 0.0)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _get_zk(self):
        self.ensure_one()
        if ZK is None:
            raise UserError(_("La bibliothèque pyzk n'est pas installée."))
        return ZK(self.device_ip, port=self.port_number,
                  timeout=self.connection_timeout, password=self.sudo().comm_key or 0,
                  force_udp=self.force_udp, ommit_ping=True)

    def _connect_device(self):
        self.ensure_one()
        try:
            conn = self._get_zk().connect()
        except UserError:
            raise
        except Exception as error:
            raise UserError(_("Impossible de se connecter à %(device)s (%(ip)s:%(port)s) : %(error)s",
                              device=self.name, ip=self.device_ip,
                              port=self.port_number, error=error)) from error
        if not conn:
            raise UserError(_("La pointeuse %s n'a pas accepté la connexion.", self.name))
        return conn

    @contextmanager
    def _device_session(self, disable=False):
        """Open a connection, optionally lock the keypad, always release it."""
        conn = self._connect_device()
        try:
            if disable:
                conn.disable_device()
            yield conn
        finally:
            try:
                if disable:
                    conn.enable_device()
                conn.disconnect()
            except Exception as error:  # the device may already have closed the socket
                _logger.warning('Biometric device %s: disconnection error: %s', self.name, error)
        self.sudo().write({'last_contact_at': fields.Datetime.now()})

    def _log(self, operation, state='success', message=False, **values):
        self.ensure_one()
        return self.env['biometric.sync.log'].sudo().create(dict(
            values, device_id=self.id, operation=operation, state=state, message=message))

    def _local_now(self):
        return datetime.now(pytz.utc).astimezone(pytz.timezone(self.timezone or 'UTC')).replace(
            tzinfo=None)

    def _notify(self, message, notification_type='success', title=False):
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': title or self.name, 'message': message,
                       'type': notification_type, 'sticky': notification_type != 'success',
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    # ------------------------------------------------------------------
    # Administration actions
    # ------------------------------------------------------------------
    def _check_direct_mode(self):
        for device in self:
            if device.connection_mode == 'relay':
                raise UserError(_(
                    "La pointeuse %s est gérée par une passerelle locale : Odoo ne peut pas "
                    "l'interroger directement. Ses informations et ses utilisateurs sont envoyés "
                    "automatiquement par la passerelle.", device.name))

    def action_test_connection(self):
        """Checking the connection status"""
        self.ensure_one()
        self._check_direct_mode()
        with self._device_session() as conn:
            name = conn.get_device_name()
        return self._notify(_('Connexion établie avec la pointeuse %s.', name or self.name))

    def action_refresh_info(self):
        """Read the hardware information, memory usage and clock of the device."""
        self._check_direct_mode()
        for device in self:
            started = time.monotonic()

            def safe(method):
                try:
                    return method()
                except Exception as error:
                    _logger.info('Biometric device %s: %s unavailable: %s',
                                 device.name, getattr(method, '__name__', method), error)
                    return False

            with device._device_session() as conn:
                values = {
                    'info_device_name': safe(conn.get_device_name) or False,
                    'info_serial': safe(conn.get_serialnumber) or False,
                    'info_firmware': safe(conn.get_firmware_version) or False,
                    'info_platform': safe(conn.get_platform) or False,
                    'info_mac': safe(conn.get_mac) or False,
                }
                safe(conn.read_sizes)
                values.update({
                    'info_user_count': getattr(conn, 'users', 0) or 0,
                    'info_user_capacity': getattr(conn, 'users_cap', 0) or 0,
                    'info_finger_count': getattr(conn, 'fingers', 0) or 0,
                    'info_finger_capacity': getattr(conn, 'fingers_cap', 0) or 0,
                    'info_face_count': getattr(conn, 'faces', 0) or 0,
                    'info_face_capacity': getattr(conn, 'faces_cap', 0) or 0,
                    'info_record_count': getattr(conn, 'records', 0) or 0,
                    'info_record_capacity': getattr(conn, 'rec_cap', 0) or 0,
                })
                device_time = safe(conn.get_time)
            if device_time:
                values['info_time_drift'] = int((device_time - device._local_now()).total_seconds())
            values['info_updated_at'] = fields.Datetime.now()
            device.write(values)
            device._log('info', message=_('Informations de la pointeuse mises à jour.'),
                        duration=time.monotonic() - started)
        return self._notify(_('Informations de la pointeuse mises à jour.'))

    def action_set_timezone(self):
        """Set the device clock to the current time of its timezone."""
        if self._queue_relay_command('set_time'):
            return self._notify(_("L'heure sera réglée par la passerelle à sa prochaine synchronisation."))
        for device in self:
            with device._device_session() as conn:
                conn.set_time(device._local_now())
            device.write({'info_time_drift': 0})
            device._log('time', message=_('Heure réglée sur %s (%s).',
                                          device._local_now().strftime('%d/%m/%Y %H:%M:%S'),
                                          device.timezone))
        return self._notify(_("Heure de la pointeuse réglée avec succès."))

    def action_restart_device(self):
        """For restarting the device"""
        if self._queue_relay_command('restart'):
            return self._notify(_('La passerelle redémarrera la pointeuse à sa prochaine synchronisation.'))
        for device in self:
            conn = device._connect_device()
            conn.restart()
            device._log('restart', message=_('Redémarrage demandé.'))
        return self._notify(_('Redémarrage de la pointeuse demandé.'))

    def action_clear_device_log(self):
        """Download the punches, then empty the device memory. Odoo keeps its data."""
        if self._queue_relay_command('clear_attendance'):
            return self._notify(_(
                'La passerelle videra la mémoire de la pointeuse juste après avoir envoyé ses '
                'pointages, à sa prochaine synchronisation.'))
        for device in self:
            started = time.monotonic()
            stats = device._download_attendance()
            with device._device_session(disable=True) as conn:
                conn.clear_attendance()
            device.write({'info_record_count': 0})
            device._log('clear', message=_(
                'Mémoire de la pointeuse vidée après import de %s nouveau(x) pointage(s). '
                'Les pointages restent conservés dans Odoo.', stats['created']),
                duration=time.monotonic() - started, records_created=stats['created'])
        return self._notify(_('Mémoire de la pointeuse vidée. Les pointages sont conservés dans Odoo.'))

    def action_reimport_attendance(self):
        """Delete the punches imported from this device and download them again."""
        for device in self:
            punches = self.env['zk.machine.attendance'].search([
                ('device_id', '=', device.id), ('source', '=', 'device')])
            employee_dates = punches._employee_dates()
            deleted = len(punches)
            punches.with_context(biometric_skip_recompute=True).unlink()
            device.last_punch_at = False
            if device.connection_mode == 'relay':
                device.relay_resend_all = True
                self.env['biometric.attendance.day']._recompute_employee_dates(employee_dates)
                device._log('reimport', message=_(
                    '%s pointage(s) supprimé(s) ; la passerelle renverra toute la mémoire de la '
                    'pointeuse à sa prochaine synchronisation.', deleted))
                continue
            stats = device._download_attendance()
            self.env['biometric.attendance.day']._recompute_employee_dates(employee_dates)
            device._log('reimport', records_read=stats['read'], records_created=stats['created'],
                        message=_('%(deleted)s pointage(s) supprimé(s), %(created)s réimporté(s).',
                                  deleted=deleted, created=stats['created']))
        return self._notify(_('Pointages réimportés depuis la pointeuse.'))

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def _match_employee(self, device_user_id, device_name):
        Employee = self.env['hr.employee']
        domain = [('company_id', 'in', [self.company_id.id, False])]
        employee = Employee.search(domain + [('device_id_num', '=', device_user_id)],
                                   order='id', limit=1)
        if not employee and device_name and device_name.strip():
            candidates = Employee.search(domain + [('name', '=ilike', device_name.strip())], limit=2)
            employee = candidates if len(candidates) == 1 else Employee
        return employee

    def _sync_device_users(self, users, quiet=False):
        """Create or update the Odoo mapping of the users stored on the device.

        Returns ``(created, updated)``.  In ``quiet`` mode (relay, every minute)
        only real changes are written.
        """
        self.ensure_one()
        DeviceUser = self.env['biometric.device.user'].sudo().with_context(active_test=False)
        existing = {mapping.device_user_id: mapping
                    for mapping in DeviceUser.search([('device_id', '=', self.id)])}
        created = updated = 0
        now = fields.Datetime.now()
        for terminal_user in users:
            device_user_id = str(terminal_user['user_id'])
            privilege = str(terminal_user.get('privilege') or 0)
            card = terminal_user.get('card')
            values = {
                'device_uid': terminal_user.get('uid') or 0,
                'device_user_name': terminal_user.get('name') or False,
                'privilege': privilege if privilege in ('0', '2', '6', '14') else '0',
                'card': str(card) if card else False,
            }
            mapping = existing.get(device_user_id)
            if mapping and quiet:
                values = {key: value for key, value in values.items()
                          if (mapping[key] or False) != (value or False)}
                if not mapping.employee_id:
                    employee = self._match_employee(device_user_id, terminal_user.get('name'))
                    if employee:
                        values['employee_id'] = employee.id
                if not values:
                    continue
            values.update({'sync_state': 'synced', 'last_synced_at': now,
                           'sync_message': _('Importé depuis la pointeuse.')})
            if mapping:
                if not quiet and not mapping.employee_id:
                    values['employee_id'] = self._match_employee(
                        device_user_id, terminal_user.get('name')).id or False
                mapping.write(values)
                updated += 1
            else:
                values.update(device_id=self.id, device_user_id=device_user_id,
                              employee_id=self._match_employee(
                                  device_user_id, terminal_user.get('name')).id or False)
                mapping = DeviceUser.create(values)
                created += 1
            if mapping.employee_id and not mapping.employee_id.device_id_num:
                mapping.employee_id.device_id_num = device_user_id
        return created, updated

    def action_import_users(self):
        """Create the Odoo mapping of every user stored on the device."""
        DeviceUser = self.env['biometric.device.user'].with_context(active_test=False)
        for device in self:
            device._check_direct_mode()
            started = time.monotonic()
            with device._device_session() as conn:
                users = conn.get_users() or []
            created, updated = device._sync_device_users([
                {'user_id': str(user.user_id), 'name': user.name, 'uid': user.uid,
                 'privilege': user.privilege, 'card': user.card} for user in users])
            unmapped = DeviceUser.search_count([('device_id', '=', device.id), ('employee_id', '=', False)])
            device._log('users_import', state='warning' if unmapped else 'success',
                        duration=time.monotonic() - started,
                        message=_('%(total)s utilisateur(s) lu(s) : %(created)s créé(s), %(updated)s mis à jour, '
                                  '%(unmapped)s sans employé associé.', total=len(users),
                                  created=created, updated=updated, unmapped=unmapped))
        return self.action_view_device_users()

    def _find_terminal_user(self, conn, device_user_id):
        return next((terminal_user for terminal_user in conn.get_users()
                     if str(terminal_user.user_id) == str(device_user_id)), None)

    def _push_device_user(self, device_user):
        self.ensure_one()
        self._check_direct_mode()
        if not device_user.employee_id:
            raise UserError(_("Associez d'abord un employé à l'identifiant %s.",
                              device_user.device_user_id))
        with self._device_session() as conn:
            try:
                # The UID belongs to the terminal: reuse the existing one, otherwise
                # let the terminal allocate the next available one.
                terminal_user = self._find_terminal_user(conn, device_user.device_user_id)
                conn.set_user(uid=terminal_user.uid if terminal_user else None,
                              name=(device_user.employee_id.name or '')[:24],
                              privilege=int(device_user.privilege),
                              password=device_user.sudo().password or '',
                              group_id='', user_id=device_user.device_user_id,
                              card=int(device_user.card or 0))
                assigned_user = self._find_terminal_user(conn, device_user.device_user_id)
            except Exception as error:
                device_user.write({'sync_state': 'error', 'sync_message': str(error)[:500],
                                   'last_synced_at': fields.Datetime.now()})
                raise UserError(_('Impossible de synchroniser %(employee)s : %(error)s',
                                  employee=device_user.employee_id.name, error=error)) from error
        values = {
            'sync_state': 'synced',
            'sync_message': _('Envoyé vers la pointeuse.'),
            'last_synced_at': fields.Datetime.now(),
            'device_user_name': (device_user.employee_id.name or '')[:24],
        }
        if assigned_user:
            values['device_uid'] = assigned_user.uid
        device_user.write(values)
        if device_user.employee_id.device_id_num != device_user.device_user_id:
            device_user.employee_id.device_id_num = device_user.device_user_id

    def _remove_device_user(self, device_user):
        self.ensure_one()
        self._check_direct_mode()
        with self._device_session() as conn:
            conn.delete_user(uid=device_user.device_uid or 0, user_id=device_user.device_user_id)
        device_user.write({'sync_state': 'pending', 'sync_message': _('Retiré de la pointeuse.'),
                           'last_synced_at': fields.Datetime.now(), 'device_uid': False})

    def action_synchronize_users(self):
        self._check_direct_mode()
        for device in self:
            users = device.device_user_ids.filtered(
                lambda device_user: device_user.active and device_user.employee_id)
            for device_user in users:
                device._push_device_user(device_user)
            device._log('users_push', message=_('%s utilisateur(s) envoyé(s).', len(users)))
        return self._notify(_('Utilisateurs envoyés vers la pointeuse.'))

    # ------------------------------------------------------------------
    # Attendance download
    # ------------------------------------------------------------------
    def _read_device(self):
        """Read the users and punches of the device (direct connection)."""
        self.ensure_one()
        with self._device_session(disable=True) as conn:
            users = conn.get_users() or []
            records = conn.get_attendance() or []
        return (
            [{'user_id': str(user.user_id), 'name': user.name, 'uid': user.uid,
              'privilege': user.privilege, 'card': user.card} for user in users],
            [{'user_id': str(record.user_id), 'timestamp': record.timestamp,
              'status': record.status, 'punch': record.punch} for record in records],
        )

    def _download_attendance(self):
        """Import the new punches of the device; return statistics."""
        self.ensure_one()
        self._check_direct_mode()
        users, records = self._read_device()
        return self._import_records(users, records)

    def _import_records(self, users, records):
        """Store the punches read from the device (directly or by the relay).

        ``users`` and ``records`` are lists of dicts; record timestamps are
        naive datetimes expressed in the device timezone.
        """
        self.ensure_one()
        # Serialise concurrent imports of the same device (cron, relays).
        self.env.cr.execute('SELECT id FROM biometric_device_details WHERE id = %s FOR UPDATE',
                            [self.id])
        tz = pytz.timezone(self.timezone or 'UTC')
        names = {user['user_id']: user.get('name') for user in users}
        Punch = self.env['zk.machine.attendance'].sudo()
        Employee = self.env['hr.employee'].sudo()
        mapping = {
            device_user.device_user_id: device_user.employee_id
            for device_user in self.device_user_ids.sudo()
            if device_user.active and device_user.employee_id
        }
        parsed = []
        for record in records:
            timestamp = record.get('timestamp')
            if not timestamp:
                continue
            if self.import_from_date and timestamp.date() < self.import_from_date:
                continue
            punch_utc = tz.localize(timestamp, is_dst=False).astimezone(pytz.utc).replace(tzinfo=None)
            parsed.append((str(record['user_id']), punch_utc, record))
        stats = {'read': len(records), 'created': 0, 'unknown': []}
        if not parsed:
            return stats

        existing = {
            (punch.device_id_num, punch.punching_time)
            for punch in Punch.search([
                ('device_id', '=', self.id),
                ('punching_time', '>=', min(item[1] for item in parsed)),
                ('punching_time', '<=', max(item[1] for item in parsed)),
            ])
        }
        missing_ids = {user_id for user_id, _time, _record in parsed if user_id not in mapping}
        by_number = {}
        if missing_ids:
            for employee in Employee.search([('device_id_num', 'in', list(missing_ids))], order='id'):
                by_number.setdefault(employee.device_id_num, employee)

        unknown, vals_list = set(), []
        valid_types = dict(Punch._fields['punch_type'].selection)
        valid_methods = dict(Punch._fields['attendance_type'].selection)
        for user_id, punch_utc, record in parsed:
            key = (user_id, punch_utc)
            if key in existing:
                continue
            employee = mapping.get(user_id) or by_number.get(user_id)
            if not employee and self.create_unknown_employee:
                employee = Employee.create({
                    'name': names.get(user_id) or _('Employé pointeuse %s', user_id),
                    'device_id_num': user_id,
                    'company_id': self.company_id.id,
                })
                by_number[user_id] = employee
            if not employee:
                unknown.add(user_id)
                continue
            existing.add(key)
            punch_type = str(record.get('punch'))
            method = str(record.get('status'))
            vals_list.append({
                'employee_id': employee.id,
                'device_id': self.id,
                'device_id_num': user_id,
                'attendance_type': method if method in valid_methods else '255',
                'punch_type': punch_type if punch_type in valid_types else '255',
                'punching_time': punch_utc,
                'address_id': self.address_id.id,
                'source': 'device',
            })
        created = Punch.with_context(biometric_skip_recompute=True).create(vals_list)
        if created:
            latest = max(created.mapped('punching_time'))
            if not self.last_punch_at or latest > self.last_punch_at:
                self.last_punch_at = latest
            self.env['biometric.attendance.day']._recompute_employee_dates(created._employee_dates())
        stats.update(created=len(created), unknown=sorted(unknown))
        return stats

    def action_download_attendance(self):
        """Function to download attendance records from the device"""
        for device in self:
            device._download_attendance()
        return True

    def _run_synchronization(self):
        """Download the punches, record the result on the device and in the log."""
        self.ensure_one()
        device = self.sudo()
        started = time.monotonic()
        previous_state = device.last_sync_state
        now = fields.Datetime.now()
        try:
            with self.env.cr.savepoint():
                stats = device._download_attendance()
        except Exception as error:
            message = str(error)[:500]
            _logger.warning('Biometric synchronization failed for %s: %s', device.display_name, message)
            device.write({'last_sync_at': now, 'last_sync_state': 'error', 'last_sync_message': message})
            if previous_state != 'error':
                device._log('download', state='error', message=message,
                            duration=time.monotonic() - started)
            return False, message
        state = 'warning' if stats['unknown'] else 'success'
        message = _('%(created)s nouveau(x) pointage(s), %(read)s en mémoire.',
                    created=stats['created'], read=stats['read'])
        if stats['unknown']:
            message += ' ' + _('Identifiants sans employé : %s.', ', '.join(stats['unknown']))
        device.write({'last_sync_at': now, 'last_sync_state': state,
                      'last_sync_message': message[:500], 'info_record_count': stats['read']})
        if stats['created'] or previous_state != state:
            device._log('download', state=state, message=message,
                        duration=time.monotonic() - started, records_read=stats['read'],
                        records_created=stats['created'],
                        unknown_user_ids=', '.join(stats['unknown']) or False)
        return True, message

    def action_synchronize_now(self):
        messages, failed = [], False
        for device in self:
            if device.connection_mode == 'relay':
                messages.append(_('%(device)s : synchronisée par la passerelle toutes les '
                                  '%(minutes)s minute(s).', device=device.name,
                                  minutes=device.sync_interval))
                continue
            success, message = device._run_synchronization()
            failed = failed or not success
            messages.append('%s : %s' % (device.name, message))
        return self._notify('\n'.join(messages), 'danger' if failed else 'success',
                            _('Synchronisation des pointages'))

    @api.model
    def cron_download(self):
        """Poll connected devices frequently; ZKTeco terminals do not push events."""
        now = fields.Datetime.now()
        for machine in self.search([('active', '=', True), ('connection_mode', '=', 'direct')]):
            if (machine.last_sync_at and
                    (now - machine.last_sync_at).total_seconds() + 5 <
                    machine.sync_interval * 60):
                continue
            machine._run_synchronization()

    # ------------------------------------------------------------------
    # Local relay (gateway PC on the site)
    # ------------------------------------------------------------------
    RELAY_COMMANDS = ('set_time', 'clear_attendance', 'restart')

    def _queue_relay_command(self, command):
        """Queue a command for relay devices; return True when queued."""
        relay_devices = self.filtered(lambda device: device.connection_mode == 'relay')
        if not relay_devices:
            return False
        if relay_devices != self:
            raise UserError(_('Traitez séparément les pointeuses en connexion directe et en passerelle.'))
        for device in relay_devices.sudo():
            commands = [name for name in (device.relay_pending_commands or '').split(',') if name]
            if command not in commands:
                commands.append(command)
            device.relay_pending_commands = ','.join(commands)
            device._log({'set_time': 'time', 'clear_attendance': 'clear',
                         'restart': 'restart'}[command], state='warning',
                        message=_('Commande « %s » transmise à la passerelle.', command))
        return True

    def action_generate_relay_token(self):
        for device in self.sudo():
            device.relay_token = secrets.token_urlsafe(32)
        return True

    def action_download_relay(self):
        self.ensure_one()
        if not self.sudo().relay_token:
            self.action_generate_relay_token()
        return {
            'type': 'ir.actions.act_url',
            'url': '/primetech_biometric/relay/package/%s' % self.id,
            'target': 'download',
        }

    def _relay_since(self):
        """Device local time from which the relay must send the punches."""
        self.ensure_one()
        if self.relay_resend_all or not self.last_punch_at:
            return False
        tz = pytz.timezone(self.timezone or 'UTC')
        local = pytz.utc.localize(self.last_punch_at).astimezone(tz).replace(tzinfo=None)
        # Margin: punches of identifiers mapped late and clock corrections.
        return (local - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

    def _relay_hello(self, payload):
        self.ensure_one()
        return {
            'ok': True,
            'device': self.name,
            'since': self._relay_since(),
            'interval': max(30, self.sync_interval * 60),
            'import_from': self.import_from_date and fields.Date.to_string(self.import_from_date),
        }

    def _relay_push(self, payload):
        """Import what the relay read from the device; return the commands to run."""
        self.ensure_one()
        started = time.monotonic()
        previous_state = self.last_sync_state
        now = fields.Datetime.now()
        users = [
            {'user_id': str(user.get('user_id')), 'name': user.get('name'), 'uid': user.get('uid'),
             'privilege': user.get('privilege'), 'card': user.get('card')}
            for user in payload.get('users') or [] if user.get('user_id') not in (None, '')
        ]
        records = []
        for record in payload.get('records') or []:
            try:
                timestamp = datetime.strptime(record['t'], '%Y-%m-%d %H:%M:%S')
            except (KeyError, TypeError, ValueError):
                continue
            records.append({'user_id': str(record.get('u')), 'timestamp': timestamp,
                            'status': record.get('s'), 'punch': record.get('p')})
        if users:
            self._sync_device_users(users, quiet=True)
        stats = self._import_records(users, records)

        info = payload.get('info') or {}
        agent = payload.get('agent') or {}
        values = {
            'last_sync_at': now,
            'last_contact_at': now,
            'relay_resend_all': False,
            'relay_agent': ('%s (v%s)' % (agent.get('host') or '?', agent.get('version') or '?'))[:120],
        }
        info_fields = {
            'device_name': 'info_device_name', 'serial': 'info_serial', 'firmware': 'info_firmware',
            'platform': 'info_platform', 'mac': 'info_mac', 'users': 'info_user_count',
            'users_cap': 'info_user_capacity', 'fingers': 'info_finger_count',
            'fingers_cap': 'info_finger_capacity', 'faces': 'info_face_count',
            'faces_cap': 'info_face_capacity', 'records': 'info_record_count',
            'records_cap': 'info_record_capacity',
        }
        for key, field_name in info_fields.items():
            if info.get(key) not in (None, ''):
                values[field_name] = info[key]
        if info.get('device_time'):
            try:
                device_time = datetime.strptime(info['device_time'], '%Y-%m-%d %H:%M:%S')
                values['info_time_drift'] = int((device_time - self._local_now()).total_seconds())
            except ValueError:
                pass
        if info:
            values['info_updated_at'] = now

        for result in payload.get('command_results') or []:
            operation = {'set_time': 'time', 'clear_attendance': 'clear',
                         'restart': 'restart'}.get(result.get('command'))
            if operation:
                self._log(operation, state='success' if result.get('ok') else 'error',
                          message=_('Passerelle : %s', result.get('message') or result.get('command')))

        state = 'warning' if stats['unknown'] else 'success'
        message = _('Passerelle %(agent)s : %(created)s nouveau(x) pointage(s), %(read)s envoyé(s).',
                    agent=agent.get('host') or '', created=stats['created'], read=stats['read'])
        if stats['unknown']:
            message += ' ' + _('Identifiants sans employé : %s.', ', '.join(stats['unknown']))
        values.update(last_sync_state=state, last_sync_message=message[:500])

        commands = [name for name in (self.relay_pending_commands or '').split(',')
                    if name in self.RELAY_COMMANDS]
        values['relay_pending_commands'] = False
        self.write(values)
        if stats['created'] or previous_state != state:
            self._log('download', state=state, message=message,
                      duration=time.monotonic() - started, records_read=stats['read'],
                      records_created=stats['created'],
                      unknown_user_ids=', '.join(stats['unknown']) or False)
        return {
            'ok': True,
            'created': stats['created'],
            'unknown': stats['unknown'],
            'since': self._relay_since(),
            'interval': max(30, self.sync_interval * 60),
            'commands': [{
                'name': name,
                'value': self._local_now().strftime('%Y-%m-%d %H:%M:%S') if name == 'set_time' else False,
            } for name in commands],
        }

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def action_view_punches(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.zk_machine_attendance_action')
        action['domain'] = [('device_id', '=', self.id)]
        return action

    def action_view_device_users(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.biometric_device_user_action')
        action['domain'] = [('device_id', 'in', self.ids)]
        action['context'] = {'default_device_id': self[:1].id, 'search_default_unmapped': 0}
        return action

    def action_view_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'primetech_biometric_attendance.biometric_sync_log_action')
        action['domain'] = [('device_id', '=', self.id)]
        return action
