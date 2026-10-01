from odoo import api, fields, models
from odoo.http import request


TRACKED_MODEL_LABELS = {
    'account.move': 'Pièce comptable',
    'account.payment': 'Paiement',
    'purchase.order': 'Bon de commande',
    'stock.picking': 'Mouvement de stock',
    'pos.order': 'Ticket de caisse',
}


class PrimetechAuditEvent(models.Model):
    _name = 'primetech.audit.event'
    _description = "Historique unifié des activités et événements d'audit"
    _order = 'event_date desc, id desc'

    event_date = fields.Datetime(string='Date / Heure', required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', required=True, default=lambda self: self.env.user, index=True)
    event_type = fields.Selection([
        ('create', 'Création'),
        ('write', 'Modification'),
        ('unlink', 'Suppression'),
        ('print', 'Impression'),
        ('event', 'Événement'),
    ], string="Type d'événement", required=True, index=True)
    action_label = fields.Char(string='Action', required=True, index=True)
    document_name = fields.Char(string='Document', index=True)
    model_name = fields.Char(string='Modèle technique', required=True, index=True)
    model_label = fields.Char(string='Module / Objet', required=True, index=True)
    res_id = fields.Integer(string='Identifiant')
    details = fields.Text(string='Détails')
    user_role = fields.Char(string='Rôle utilisateur')
    ip_address = fields.Char(string='Adresse IP')
    device_info = fields.Char(string='Navigateur / Appareil')

    def open_document(self):
        self.ensure_one()
        if not self.res_id or self.model_name not in self.env.registry or not self.env[self.model_name].browse(self.res_id).exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.document_name or self.model_label,
            'res_model': self.model_name,
            'res_id': self.res_id,
            'view_mode': 'form',
        }

    @api.model
    def log_event(self, event_type, action_label, model_name, model_label=None, res_id=0, document_name=None, details=None):
        if self.env.context.get('primetech_skip_audit'):
            return False
        ip_address, device_info = self._request_metadata()
        return self.sudo().with_context(primetech_skip_audit=True).create({
            'event_type': event_type,
            'action_label': action_label,
            'model_name': model_name,
            'model_label': model_label or TRACKED_MODEL_LABELS.get(model_name, model_name),
            'res_id': res_id or 0,
            'document_name': document_name or '-',
            'details': details,
            'user_id': self.env.uid,
            'user_role': self._user_role(),
            'ip_address': ip_address,
            'device_info': device_info,
        })

    @api.model
    def _user_role(self):
        profile_groups = self.env.user.groups_id.filtered(lambda group: (group.name or '').startswith('Profil :'))
        return (profile_groups[:1].name or '').replace('Profil :', '').strip() if profile_groups else 'Utilisateur'

    @api.model
    def _request_metadata(self):
        try:
            httprequest = request.httprequest
            forwarded_for = httprequest.headers.get('X-Forwarded-For', '')
            ip_address = forwarded_for.split(',')[0].strip() or httprequest.remote_addr or '-'
            user_agent = httprequest.user_agent
            device_info = f'{user_agent.browser or "Navigateur"} / {user_agent.platform or "Appareil"}'
            return ip_address, device_info
        except (RuntimeError, AttributeError):
            return '-', 'Traitement serveur'


class PrimetechAuditMixin(models.AbstractModel):
    _name = 'primetech.audit.mixin'
    _description = "Journalisation des opérations métier"

    def _audit_document_name(self):
        self.ensure_one()
        return getattr(self, 'name', False) or self.display_name

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('primetech_skip_audit'):
            for record in records:
                self.env['primetech.audit.event'].log_event(
                    'create', f"Création — {record._audit_document_name()}", record._name,
                    res_id=record.id, document_name=record._audit_document_name(),
                )
        return records

    def write(self, vals):
        result = super().write(vals)
        if result and vals and not self.env.context.get('primetech_skip_audit'):
            labels = [self._fields[name].string for name in vals if name in self._fields]
            details = 'Champs modifiés : ' + ', '.join(labels[:20])
            for record in self:
                name = record._audit_document_name()
                self.env['primetech.audit.event'].log_event(
                    'write', f"Modification — {name}", record._name,
                    res_id=record.id, document_name=name, details=details,
                )
        return result

    def unlink(self):
        snapshots = [(record.id, record._audit_document_name()) for record in self]
        model_name = self._name
        result = super().unlink()
        if result and not self.env.context.get('primetech_skip_audit'):
            for res_id, name in snapshots:
                self.env['primetech.audit.event'].log_event(
                    'unlink', f"Suppression — {name}", model_name,
                    document_name=name, details=f'Identifiant supprimé : {res_id}',
                )
        return result


def _audit_document_name(record):
    return getattr(record, 'name', False) or record.display_name


def _audit_after_create(records):
    if records.env.context.get('primetech_skip_audit'):
        return
    for record in records:
        name = _audit_document_name(record)
        record.env['primetech.audit.event'].log_event(
            'create', f"Création — {name}", record._name,
            res_id=record.id, document_name=name,
        )


def _audit_after_write(records, vals):
    if not vals or records.env.context.get('primetech_skip_audit'):
        return
    labels = [records._fields[name].string for name in vals if name in records._fields]
    details = 'Champs modifiés : ' + ', '.join(labels[:20])
    for record in records:
        name = _audit_document_name(record)
        record.env['primetech.audit.event'].log_event(
            'write', f"Modification — {name}", record._name,
            res_id=record.id, document_name=name, details=details,
        )


def _audit_after_unlink(env, snapshots, model_name):
    if env.context.get('primetech_skip_audit'):
        return
    for res_id, name in snapshots:
        env['primetech.audit.event'].log_event(
            'unlink', f"Suppression — {name}", model_name,
            document_name=name, details=f'Identifiant supprimé : {res_id}',
        )


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _audit_after_create(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if result:
            _audit_after_write(self, vals)
        return result

    def unlink(self):
        snapshots = [(record.id, _audit_document_name(record)) for record in self]
        model_name = self._name
        env = self.env
        result = super().unlink()
        if result:
            _audit_after_unlink(env, snapshots, model_name)
        return result


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _audit_after_create(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if result:
            _audit_after_write(self, vals)
        return result

    def unlink(self):
        snapshots = [(record.id, _audit_document_name(record)) for record in self]
        model_name = self._name
        env = self.env
        result = super().unlink()
        if result:
            _audit_after_unlink(env, snapshots, model_name)
        return result


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _audit_after_create(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if result:
            _audit_after_write(self, vals)
        return result

    def unlink(self):
        snapshots = [(record.id, _audit_document_name(record)) for record in self]
        model_name = self._name
        env = self.env
        result = super().unlink()
        if result:
            _audit_after_unlink(env, snapshots, model_name)
        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _audit_after_create(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if result:
            _audit_after_write(self, vals)
        return result

    def unlink(self):
        snapshots = [(record.id, _audit_document_name(record)) for record in self]
        model_name = self._name
        env = self.env
        result = super().unlink()
        if result:
            _audit_after_unlink(env, snapshots, model_name)
        return result


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _audit_after_create(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if result:
            _audit_after_write(self, vals)
        return result

    def unlink(self):
        snapshots = [(record.id, _audit_document_name(record)) for record in self]
        model_name = self._name
        env = self.env
        result = super().unlink()
        if result:
            _audit_after_unlink(env, snapshots, model_name)
        return result


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        result = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        report = self._get_report(report_ref)
        for res_id in res_ids or []:
            record = self.env[report.model].browse(res_id) if report.model in self.env.registry else False
            document_name = record.display_name if record and record.exists() else str(res_id)
            self.env['primetech.audit.event'].log_event(
                'print', f"Impression — {report.name}: {document_name}", report.model,
                model_label=report.name, res_id=res_id, document_name=document_name,
                details='Génération PDF',
            )
        return result
