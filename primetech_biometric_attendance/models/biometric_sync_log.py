# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class BiometricSyncLog(models.Model):
    _name = 'biometric.sync.log'
    _description = 'Journal des pointeuses'
    _order = 'date desc, id desc'
    _rec_name = 'date'

    device_id = fields.Many2one('biometric.device.details', string='Pointeuse',
                                required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='device_id.company_id', store=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True, index=True)
    operation = fields.Selection([
        ('download', 'Téléchargement des pointages'),
        ('users_import', 'Import des utilisateurs'),
        ('users_push', 'Envoi des utilisateurs'),
        ('info', 'Lecture des informations'),
        ('time', "Réglage de l'heure"),
        ('clear', 'Vidage de la mémoire'),
        ('reimport', 'Réimport des pointages'),
        ('restart', 'Redémarrage'),
    ], string='Opération', required=True, default='download')
    state = fields.Selection([('success', 'Réussi'), ('warning', 'Avertissement'),
                              ('error', 'Erreur')], string='Résultat', required=True,
                             default='success')
    duration = fields.Float(string='Durée (s)', digits=(6, 2))
    records_read = fields.Integer(string='Pointages lus')
    records_created = fields.Integer(string='Nouveaux pointages')
    unknown_user_ids = fields.Char(string='Identifiants inconnus')
    message = fields.Text(string='Détails')
    user_id = fields.Many2one('res.users', string='Lancé par', default=lambda self: self.env.uid)

    @api.autovacuum
    def _gc_old_logs(self):
        for company in self.env['res.company'].search([]):
            retention = company.biometric_log_retention_days or 90
            self.search([
                ('company_id', '=', company.id),
                ('date', '<', fields.Datetime.now() - timedelta(days=retention)),
            ]).unlink()
