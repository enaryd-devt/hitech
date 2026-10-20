from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _check_customer_cash_payment_access(self):
        """Keep cash operations unavailable to POS sellers, even by RPC."""
        if self.env.user.has_group("primetech_pos_hitech_theme.group_pos_seller"):
            raise UserError(_(
                "Le rôle vendeur ne peut pas effectuer de mouvement de caisse "
                "ni consulter les paiements partenaires POS."
            ))

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

    def _set_payment_label(self, payment, label):
        """Keep the POS description on both the payment and partner entry."""
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
    def pos_customer_payment_partners(self, session_id, search_term="", offset=0, limit=100):
        """Search every active contact available to the POS user, by pages."""
        self._check_customer_cash_payment_access()
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
        self._check_customer_cash_payment_access()
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
    def create_customer_cash_payment(self, session_id, partner_id, payment_type, amount, reason=""):
        self._check_customer_cash_payment_access()
        session = self.browse(session_id).exists()
        if not session or session.state not in ("opened", "opening_control"):
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        if payment_type not in ("inbound", "outbound") or amount <= 0:
            raise ValidationError(_("Le montant du paiement doit être supérieur à zéro."))
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            raise ValidationError(_("Veuillez sélectionner un partenaire."))
        journal = session.cash_journal_id
        if not journal:
            raise UserError(_("Aucun journal de caisse n'est configuré pour cette session POS."))
        suspense_account = journal.suspense_account_id
        if not suspense_account:
            raise UserError(_("Configurez un compte d'attente sur le journal de caisse du POS."))

        before, before_direction = session._pos_partner_global_balance(partner)
        # ``payment.name`` is allocated only when the payment is posted.  A
        # temporary value is used at creation and the final, human-readable
        # label is written immediately afterwards on the partner journal item.
        payment_label = reason or (
            _("Paiement POS %(session)s - %(partner)s")
            % {"session": session.name, "partner": partner.display_name}
        )
        payment = self.env["account.payment"].create({
            "payment_type": payment_type,
            # The cash direction determines the partner account.  No account
            # is selected by the cashier and no invoice is reconciled here.
            "partner_type": "customer" if payment_type == "inbound" else "supplier",
            "partner_id": partner.commercial_partner_id.id,
            "amount": amount,
            "currency_id": session.currency_id.id,
            "date": fields.Date.context_today(session),
            "journal_id": journal.id,
            "payment_method_line_id": session._get_payment_method_line(journal, payment_type).id,
            "force_outstanding_account_id": suspense_account.id if suspense_account else False,
            "payment_reference": payment_label,
            "memo": payment_label,
            "pos_session_id": session.id,
            "pos_customer_cash_payment": True,
            "pos_balance_before": before,
            "pos_balance_before_direction": before_direction,
        })
        payment.action_post()
        payment_label = " - ".join(
            part for part in (session.name, payment.name, reason) if part
        )
        session._set_payment_label(payment, payment_label)
        # This line is deliberately retained for the cash journal: POS closing uses it to calculate the
        # physical cash expected in the drawer.  It clears the payment's suspense
        # line, so the cash and receivable are each recorded exactly once.
        sign = 1 if payment_type == "inbound" else -1
        statement_line = self.env["account.bank.statement.line"].create({
            "pos_session_id": session.id, "journal_id": journal.id, "amount": sign * amount,
            "date": fields.Date.context_today(session), "payment_ref": payment_label,
            # The accounting payment already owns the partner line.  Do not
            # set a partner on this technical cash entry.
            "partner_id": False,
            "counterpart_account_id": suspense_account.id,
            "pos_customer_cash_payment_id": payment.id,
        })
        suspense_lines = payment.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled) | statement_line.move_id.line_ids.filtered(lambda line: line.account_id == suspense_account and not line.reconciled)
        # Clear the technical bridge; this does not reconcile partner invoices.
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
            "reason": payment.payment_reference or "",
            # Keep the original payment timestamp when displaying or reprinting
            # an entry from the POS history.
            "date": fields.Datetime.context_timestamp(
                self, payment.create_date
            ).strftime("%d/%m/%Y %H:%M"),
        }

    @api.model
    def pos_customer_payment_list(self, session_id, offset=0, limit=50, search_term=""):
        """Return paginated partner payments from every POS session."""
        self._check_customer_cash_payment_access()
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        domain = [("pos_customer_cash_payment", "=", True)]
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
        limit = max(1, min(int(limit or 50), 50))
        payments = self.env["account.payment"].search(domain, order="id desc", offset=offset, limit=limit)
        return {
            "payments": [self._payment_receipt_values(payment) for payment in payments],
            "total": total,
        }

    @api.model
    def pos_cash_move_list(self, session_id, offset=0, limit=50, search_term=""):
        """Return the cash entries and exits of the current POS session."""
        self._check_customer_cash_payment_access()
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        domain = [
            ("pos_session_id", "=", session.id),
            ("journal_id", "=", session.cash_journal_id.id),
        ]
        search_term = (search_term or "").strip()
        if search_term:
            domain += [
                "|", "|", "|",
                ("payment_ref", "ilike", search_term),
                ("ref", "ilike", search_term),
                ("name", "ilike", search_term),
                ("pos_customer_cash_payment_id.partner_id", "ilike", search_term),
            ]
        statement_lines = self.env["account.bank.statement.line"]
        total = statement_lines.search_count(domain)
        offset = max(0, int(offset or 0))
        limit = max(1, min(int(limit or 50), 50))
        moves = statement_lines.search(domain, order="date desc, id desc", offset=offset, limit=limit)
        # Totals apply to all displayed-session movements (and, when a search
        # is active, to its result set), not just to the current page.  Let
        # PostgreSQL aggregate them so the view stays fast on long sessions.
        inbound_group = statement_lines.read_group(
            domain + [("amount", ">", 0)], ["amount:sum"], []
        )
        outbound_group = statement_lines.read_group(
            domain + [("amount", "<", 0)], ["amount:sum"], []
        )
        inbound_total = inbound_group[0].get("amount", 0.0) if inbound_group else 0.0
        outbound_total = abs(outbound_group[0].get("amount", 0.0)) if outbound_group else 0.0
        result = []
        for move in moves:
            payment = move.pos_customer_cash_payment_id
            result.append({
                "id": move.id,
                "date": fields.Datetime.context_timestamp(self, move.create_date).strftime("%d/%m/%Y %H:%M"),
                "partner_name": payment.partner_id.display_name if payment else (move.partner_id.display_name or ""),
                "label": payment.payment_reference if payment else (move.payment_ref or move.ref or move.name or ""),
                "document_number": payment.name if payment else "",
                "amount": abs(move.amount),
                "direction": "inbound" if move.amount >= 0 else "outbound",
                "receipt": self._payment_receipt_values(payment) if payment else False,
            })
        return {
            "moves": result,
            "total": total,
            "inbound_total": inbound_total,
            "outbound_total": outbound_total,
        }
