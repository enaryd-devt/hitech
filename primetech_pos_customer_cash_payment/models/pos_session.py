from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _pos_partner_global_balance(self, partner):
        """Return the partner's global customer and supplier position.

        A partner can be both customer and supplier.  The receipt must reflect
        the net of both ledgers, not just the account selected for a payment.
        ``amount_residual`` keeps partial reconciliations accurate.
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
        signed_balance = sum(lines.mapped("amount_residual"))
        if not signed_balance:
            direction = "settled"
        else:
            direction = "partner_owes" if signed_balance > 0 else "company_owes"
        return abs(signed_balance), direction

    def _get_payment_method_line(self, journal, payment_type):
        lines = journal.inbound_payment_method_line_ids if payment_type == "inbound" else journal.outbound_payment_method_line_ids
        if not lines:
            raise UserError(_("Configurez une méthode de paiement entrant et sortant sur le journal sélectionné."))
        return lines[:1]

    def _reconcile_partner_payment(self, payment):
        """Reconcile the payment from the oldest posted partner invoice onward."""
        partner_account_type = (
            "asset_receivable"
            if payment.partner_type == "customer"
            else "liability_payable"
        )
        payment_line = payment.move_id.line_ids.filtered(
            lambda line: (
                line.account_id.account_type == partner_account_type
                and line.partner_id.commercial_partner_id == payment.partner_id.commercial_partner_id
                and not line.reconciled
            )
        )
        if not payment_line:
            return False
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
                lambda line: (
                    line.account_id.account_type == partner_account_type
                    and line.partner_id.commercial_partner_id == payment.partner_id.commercial_partner_id
                    and not line.reconciled
                )
            )
        return True

    def _set_payment_reconciliation_label(self, payment, label):
        """Keep the POS description visible in the manual reconciliation UI.

        The reconciliation widget displays the label of the partner journal
        item (``account.move.line.name``), not only ``payment_reference``.
        Set both values so the posted POS payment is immediately identifiable
        alongside the invoices it has settled.
        """
        partner_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in (
                "asset_receivable",
                "liability_payable",
            )
        )
        payment.move_id.write({"ref": label})
        if partner_lines:
            partner_lines.write({"name": label})

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
    def pos_partner_global_balance(self, session_id, partner_id):
        """Provide the live global partner position to the POS JavaScript UI."""
        session = self.browse(session_id).exists()
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not session or not partner:
            raise ValidationError(_("Veuillez sélectionner un partenaire."))
        amount, direction = session._pos_partner_global_balance(partner)
        labels = {
            "partner_owes": _("Le partenaire nous doit"),
            "company_owes": _("Nous devons au partenaire"),
            "settled": _("Solde réglé"),
        }
        return {
            "partner_name": partner.commercial_partner_id.display_name,
            "amount": amount,
            "direction": labels[direction],
            "direction_code": direction,
        }

    @api.model
    def create_customer_cash_payment(self, session_id, partner_id, payment_type, amount, reason="", pos_payment_method_id=False, partner_type=False):
        session = self.browse(session_id).exists()
        if not session or session.state not in ("opened", "opening_control"):
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        if payment_type not in ("inbound", "outbound") or amount <= 0:
            raise ValidationError(_("Le montant du paiement doit être supérieur à zéro."))
        if partner_type not in ("customer", "supplier", "manual", False, ""):
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

        before, before_direction = session._pos_partner_global_balance(partner)
        # The reconciliation account is deliberately chosen by the cashier.
        # If it is Client or Fournisseur, the payment is reconciled below;
        # when it is empty/manual, no invoice is touched.
        manual_reconciliation = partner_type in ("manual", False, "")
        reconciliation_partner_type = partner_type
        # ``payment.name`` is allocated only when the payment is posted.  A
        # temporary value is used at creation and the final, human-readable
        # label is written immediately afterwards on the partner journal item.
        reconciliation_label = reason or (
            _("Paiement POS %(session)s - %(partner)s")
            % {"session": session.name, "partner": partner.display_name}
        )
        payment = self.env["account.payment"].create({
            "payment_type": payment_type,
            # This controls the receivable/payable account selected by Odoo for
            # the payment and therefore the account reconciled below.
            "partner_type": (
                "customer" if manual_reconciliation else reconciliation_partner_type
            ),
            "partner_id": partner.commercial_partner_id.id,
            "amount": amount,
            "currency_id": session.currency_id.id,
            "date": fields.Date.context_today(session),
            "journal_id": journal.id,
            "payment_method_line_id": session._get_payment_method_line(journal, payment_type).id,
            "force_outstanding_account_id": suspense_account.id if suspense_account else False,
            "payment_reference": reconciliation_label,
            "memo": reconciliation_label,
            "pos_session_id": session.id,
            "pos_customer_cash_payment": True,
            "pos_payment_method_id": pos_payment_method.id,
            "pos_manual_reconciliation": manual_reconciliation,
            "pos_balance_before": before,
            "pos_balance_before_direction": before_direction,
        })
        payment.action_post()
        reconciliation_label = " - ".join(
            part for part in (session.name, payment.name, reason) if part
        )
        session._set_payment_reconciliation_label(payment, reconciliation_label)
        # The payment is matched from the oldest invoice to the newest.  If no
        # invoice is open, no reconciliation happens: it remains an open credit
        # (or debit) on the selected partner account for a future invoice.
        if not manual_reconciliation:
            session._reconcile_partner_payment(payment)

        # This line is deliberately retained for the cash journal: POS closing uses it to calculate the
        # physical cash expected in the drawer.  It clears the payment's suspense
        # line, so the cash and receivable are each recorded exactly once.
        if journal == session.cash_journal_id:
            sign = 1 if payment_type == "inbound" else -1
            statement_line = self.env["account.bank.statement.line"].create({
                "pos_session_id": session.id, "journal_id": journal.id, "amount": sign * amount,
                # This is also the label of the technical cash statement
                # entry displayed in the reconciliation kanban.  It must
                # carry the POS reason just like the partner payment line.
                "date": fields.Date.context_today(session), "payment_ref": reconciliation_label,
                # For an automatic invoice settlement, the statement entry is
                # a technical cash movement only.  Without a selected account
                # it follows the native cash flow and keeps the chosen partner
                # visible as an outstanding reconciliation item.
                "partner_id": (
                    False
                    if not manual_reconciliation
                    else partner.commercial_partner_id.id
                ),
                "counterpart_account_id": suspense_account.id,
            })
            suspense_lines = payment.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled) | statement_line.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled)
            # Only a payment explicitly tied to a customer/supplier account
            # clears this technical bridge automatically.  Otherwise retain
            # the native pending cash movement for later manual matching.
            if not manual_reconciliation:
                if suspense_lines and not suspense_account.reconcile:
                    suspense_account.sudo().write({"reconcile": True})
                if suspense_lines:
                    suspense_lines.reconcile()
        # Every accounting entry of this operation now exists; the value shown
        # on the receipt is the real balance after this incoming/outgoing payment.
        after, after_direction = session._pos_partner_global_balance(partner)
        payment.write({
            "pos_balance_after": after,
            "pos_balance_after_direction": after_direction,
        })
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
            "balance_before_label": payment._pos_balance_direction_label(
                payment.pos_balance_before_direction
            ),
            "balance_after_label": payment._pos_balance_direction_label(
                payment.pos_balance_after_direction
            ),
            "partner_type": payment.partner_type,
            "payment_type": payment.payment_type,
            "manual_reconciliation": payment.pos_manual_reconciliation,
            "payment_method_name": payment.pos_payment_method_id.name or payment.journal_id.name,
            "reconciliation_account": _("Lettrage manuel") if payment.pos_manual_reconciliation else (_("Compte client") if payment.partner_type == "customer" else _("Compte fournisseur")),
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
