from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _pos_customer_balance(self, partner):
        """Return the live open balance of the partner's accounting account.

        ``amount_residual`` is essential: summing the line balance would show
        the original invoice amount after a partial reconciliation.  This
        includes every posted open receivable/payable line of the commercial
        partner: invoices, payments and statement-related entries.
        """
        self.ensure_one()
        commercial_partner = partner.commercial_partner_id
        lines = self.env["account.move.line"].search([
            ("partner_id", "child_of", commercial_partner.id),
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
        ])
        return sum(lines.mapped("amount_residual"))

    def _get_payment_method_line(self, journal, payment_type):
        lines = journal.inbound_payment_method_line_ids if payment_type == "inbound" else journal.outbound_payment_method_line_ids
        if not lines:
            raise UserError(_("Configurez une méthode de paiement entrant et sortant sur le journal sélectionné."))
        return lines[:1]

    def _reconcile_partner_payment(self, payment):
        """Reconcile the payment from the oldest posted partner invoice onward."""
        payment_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.destination_account_id and not line.reconciled
        )
        if not payment_line:
            return
        # The account selected (customer or supplier), rather than the cash
        # direction, determines the accounting sign of the payment line.
        residual_operator = "<" if payment_line.amount_residual > 0 else ">"
        invoice_types = (
            ("out_invoice", "out_refund")
            if payment.partner_type == "customer"
            else ("in_invoice", "in_refund")
        )
        open_lines = self.env["account.move.line"].search([
            ("partner_id", "child_of", payment.partner_id.commercial_partner_id.id),
            ("account_id", "=", payment.destination_account_id.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("amount_residual", residual_operator, 0),
            ("move_id", "!=", payment.move_id.id),
            ("move_id.move_type", "in", invoice_types),
        # Apply the POS payment to the oldest posted invoice first.
        ], order="date_maturity asc, date asc, id asc")
        for open_line in open_lines:
            if not payment_line or payment_line.amount_residual == 0:
                break
            (payment_line | open_line).reconcile()
            payment_line = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.destination_account_id and not line.reconciled
            )

    @api.model
    def pos_customer_payment_methods(self, session_id):
        """Payment modes enabled on this POS and usable for partner payments."""
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        return [{"id": method.id, "name": method.name} for method in session.config_id.payment_method_ids.filtered("journal_id")]

    @api.model
    def pos_customer_payment_partners(self, session_id, search_term="", offset=0, limit=100):
        """Search every active contact available to the POS user, by pages."""
        session = self.browse(session_id).exists()
        if not session:
            return {"partners": [], "has_more": False}
        # display_name is computed/non-stored in Odoo 18 and cannot be used
        # in a SQL ORDER BY.
        domain = [("active", "=", True)]
        if search_term:
            domain += ["|", "|", "|", "|", ("name", "ilike", search_term), ("phone", "ilike", search_term), ("mobile", "ilike", search_term), ("email", "ilike", search_term), ("ref", "ilike", search_term)]
        partners = self.env["res.partner"].search(domain, order="name, id", offset=offset, limit=limit + 1)
        has_more = len(partners) > limit
        return {
            "partners": partners[:limit].read(["display_name", "name", "phone", "mobile", "email", "ref"]),
            "has_more": has_more,
        }

    @api.model
    def create_customer_cash_payment(self, session_id, partner_id, payment_type, amount, reason="", pos_payment_method_id=False, partner_type=False):
        session = self.browse(session_id).exists()
        if not session or session.state not in ("opened", "opening_control"):
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        if payment_type not in ("inbound", "outbound") or amount <= 0:
            raise ValidationError(_("Le montant du paiement doit être supérieur à zéro."))
        if partner_type not in ("customer", "supplier"):
            raise ValidationError(_("Veuillez sélectionner le compte client ou fournisseur à lettrer."))
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            raise ValidationError(_("Veuillez sélectionner un partenaire."))
        pos_payment_method = session.config_id.payment_method_ids.filtered(lambda method: method.id == int(pos_payment_method_id or 0))
        if not pos_payment_method:
            raise ValidationError(_("Veuillez sélectionner un mode de paiement configuré sur ce POS."))
        journal = pos_payment_method.journal_id
        if not journal:
            raise UserError(_("Le mode de paiement sélectionné n'a pas de journal comptable."))
        suspense_account = journal.suspense_account_id if journal == session.cash_journal_id else False
        if journal == session.cash_journal_id and not suspense_account:
            raise UserError(_("Configurez un compte d'attente sur le journal de caisse du POS."))

        before = session._pos_customer_balance(partner)
        payment = self.env["account.payment"].create({
            "payment_type": payment_type,
            # This controls the receivable/payable account selected by Odoo for
            # the payment and therefore the account reconciled below.
            "partner_type": partner_type,
            "partner_id": partner.commercial_partner_id.id,
            "amount": amount,
            "currency_id": session.currency_id.id,
            "date": fields.Date.context_today(session),
            "journal_id": journal.id,
            "payment_method_line_id": session._get_payment_method_line(journal, payment_type).id,
            "force_outstanding_account_id": suspense_account.id if suspense_account else False,
            "payment_reference": reason or _("Paiement partenaire au POS"),
            "memo": reason or _("Paiement partenaire au POS"),
            "pos_session_id": session.id,
            "pos_customer_cash_payment": True,
            "pos_balance_before": before,
        })
        payment.action_post()
        # The payment is matched from the oldest invoice to the newest.  If no
        # invoice is open, no reconciliation happens: it remains an open credit
        # (or debit) on the selected partner account for a future invoice.
        session._reconcile_partner_payment(payment)

        # This line is deliberately retained for the cash journal: POS closing uses it to calculate the
        # physical cash expected in the drawer.  It clears the payment's suspense
        # line, so the cash and receivable are each recorded exactly once.
        if journal == session.cash_journal_id:
            sign = 1 if payment_type == "inbound" else -1
            statement_line = self.env["account.bank.statement.line"].create({
                "pos_session_id": session.id, "journal_id": journal.id, "amount": sign * amount,
                "date": fields.Date.context_today(session), "payment_ref": "%s - %s" % (session.name, payment.name),
                "partner_id": partner.commercial_partner_id.id, "counterpart_account_id": suspense_account.id,
            })
            suspense_lines = payment.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled) | statement_line.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled)
            # A cash journal's suspense account is frequently not reconcilable
            # (for example account 521002).  The partner payment remains valid;
            # clear the cash lines only when the account allows reconciliation.
            if suspense_lines and suspense_account.reconcile:
                suspense_lines.reconcile()
        # Every accounting entry of this operation now exists; the value shown
        # on the receipt is the real balance after this incoming/outgoing payment.
        payment.pos_balance_after = session._pos_customer_balance(partner)
        return self._payment_receipt_values(payment)

    @api.model
    def _payment_receipt_values(self, payment):
        payment.ensure_one()
        return {
            "id": payment.id,
            "name": payment.name,
            "partner_name": payment.partner_id.display_name,
            "amount": payment.amount,
            "balance_before": payment.pos_balance_before,
            "balance_after": payment.pos_balance_after,
            "payment_type": payment.payment_type,
            "reason": payment.payment_reference or "",
            # Keep the original payment timestamp when displaying or reprinting
            # an entry from the POS history.
            "date": fields.Datetime.context_timestamp(
                self, payment.create_date
            ).strftime("%d/%m/%Y %H:%M"),
        }

    @api.model
    def pos_customer_payment_list(self, session_id, offset=0, limit=150, search_term=""):
        """Return paginated customer payments for every session of this POS."""
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        domain = [
            ("pos_session_id.config_id", "=", session.config_id.id),
            ("pos_customer_cash_payment", "=", True),
        ]
        search_term = (search_term or "").strip()
        if search_term:
            domain += [
                "|", "|",
                ("partner_id", "ilike", search_term),
                ("name", "ilike", search_term),
                ("payment_reference", "ilike", search_term),
            ]
        total = self.env["account.payment"].search_count(domain)
        offset = max(0, int(offset or 0))
        # Sending the displayed total as the limit shows every payment;
        # otherwise the client uses 150 compact rows per page by default.
        limit = max(1, min(int(limit or 150), total or 1))
        payments = self.env["account.payment"].search(domain, order="id desc", offset=offset, limit=limit)
        return {
            "payments": [self._payment_receipt_values(payment) for payment in payments],
            "total": total,
        }
