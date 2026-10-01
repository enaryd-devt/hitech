from odoo import http
from odoo.http import request


class PrimetechAuditController(http.Controller):

    @http.route('/primetech/audit/dashboard-action', type='json', auth='user', methods=['POST'])
    def audit_dashboard_action(self, action_label=None, model_name=None, model_label=None, document_name=None, details=None):
        """Record dashboard consultations without blocking the clicked action."""
        action_label = (action_label or 'Consultation').strip()[:255]
        model_name = (model_name or 'primetech.dashboard').strip()[:255]
        model_label = (model_label or 'Tableau de bord').strip()[:255]
        document_name = (document_name or action_label).strip()[:255]
        details = (details or 'Consultation depuis le tableau de bord.').strip()
        request.env['primetech.audit.event'].log_event(
            'event',
            action_label,
            model_name,
            model_label=model_label,
            document_name=document_name,
            details=details,
        )
        return True

    @http.route('/primetech/audit/pos-receipt', type='json', auth='user', methods=['POST'])
    def audit_pos_receipt(self, order_id=None, order_name=None):
        numeric_order_id = int(order_id) if str(order_id or '').isdigit() else 0
        order = request.env['pos.order'].browse(numeric_order_id).exists() if numeric_order_id else False
        name = (order and order.display_name) or order_name or 'Ticket de caisse'
        request.env['primetech.audit.event'].log_event(
            'print', f"Impression du ticket de caisse — {name}", 'pos.order',
            model_label='Point de vente', res_id=order.id if order else 0,
            document_name=name, details='Impression ou réimpression depuis le point de vente',
        )
        return True
