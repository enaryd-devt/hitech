from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class PosSession(models.Model):
    _inherit = "pos.session"

    primetech_mobile_money_opening_balances = fields.Json(
        string="Soldes d'ouverture Mobile Money",
        readonly=True,
        copy=False,
        default=dict,
    )
    primetech_mobile_money_closing_balances = fields.Json(
        string="Soldes de clôture Mobile Money",
        readonly=True,
        copy=False,
        default=dict,
    )

    def _primetech_wallet_balance(self, payment_method):
        """Return the non-negative available balance of a wallet journal."""
        if not payment_method or not payment_method.journal_id:
            return False
        balance, _line_count = payment_method.journal_id._get_journal_bank_account_balance()
        return max(0.0, balance)

    def _primetech_wallet_available_balance(self, payment_method):
        """Session wallet balance: opening count + transfers + customer payments."""
        self.ensure_one()
        opening_balances = self.primetech_mobile_money_opening_balances or {}
        opening_key = str(payment_method.id)
        # A session opened before this feature has no saved opening count: in
        # that case, retain the accounting-journal balance as a safe fallback.
        opening_balance = (
            float(opening_balances[opening_key])
            if opening_key in opening_balances
            else self._primetech_wallet_balance(payment_method)
        )
        if opening_balance is False:
            return False
        transfer_amount = sum(
            self._primetech_mobile_money_session_moves(payment_method).mapped("amount")
        )
        pending_customer_payments = self._get_closed_orders().payment_ids.filtered(
            lambda payment: payment.payment_method_id == payment_method
        )
        return max(
            0.0,
            opening_balance + transfer_amount + sum(pending_customer_payments.mapped("amount")),
        )

    def _primetech_mobile_money_session_moves(self, payment_method):
        """Return the transfer lines of this session for one wallet method."""
        self.ensure_one()
        return self.env["account.bank.statement.line"].sudo().search(
            [
                ("primetech_mobile_money_session_id", "=", self.id),
                ("journal_id", "=", payment_method.journal_id.id),
                ("primetech_mobile_money_provider", "=", payment_method.primetech_mobile_money_type),
            ],
            order="create_date, id",
        )

    @api.model
    def primetech_mobile_money_balances(self, session_id):
        """Balances displayed in the POS transaction popup before validation."""
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus ouverte."))
        methods = session.config_id.payment_method_ids
        cash_method = methods.filtered(
            lambda method: method.primetech_mobile_money_type == "cash"
        )[:1]
        return {
            "cash": max(0.0, session.cash_register_balance_end) if cash_method else False,
            "wallets": [{
                "id": method.id,
                "name": method.name,
                "provider": method.primetech_mobile_money_type,
                "balance": session._primetech_wallet_available_balance(method),
            } for method in methods.filtered(lambda method: method.primetech_mobile_money_type in ("orange", "momo"))],
        }

    @api.model
    def primetech_mobile_money_transaction_list(self, session_id, filters=None):
        """Manager-only, POS-friendly transaction list with server filtering."""
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La session du point de vente n'est plus disponible."))
        if not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Seul un responsable du point de vente peut consulter cette liste."))
        filters = filters or {}
        domain = [("primetech_mobile_money_provider", "!=", False)]
        if filters.get("search"):
            domain.extend(["|", ("payment_ref", "ilike", filters["search"]), ("partner_id", "ilike", filters["search"])])
        if filters.get("provider") in ("orange", "momo"):
            domain.append(("primetech_mobile_money_provider", "=", filters["provider"]))
        if filters.get("operation") in ("withdrawal", "deposit"):
            domain.append(("primetech_mobile_money_operation", "=", filters["operation"]))
        if filters.get("date_from"):
            domain.append(("date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            domain.append(("date", "<=", filters["date_to"]))
        transactions = self.env["account.bank.statement.line"].sudo().search(domain, order="date desc, id desc", limit=200)
        return [{
            "id": transaction.id,
            "date": fields.Date.to_string(transaction.date),
            "date_time": fields.Datetime.context_timestamp(
                self, transaction.create_date
            ).strftime("%d/%m/%Y %H:%M:%S"),
            "reference": transaction.payment_ref or "/",
            "partner": transaction.partner_id.name or "",
            "payment_method": transaction.primetech_mobile_money_payment_method_id.name or "",
            "provider": transaction.primetech_mobile_money_provider == "orange" and _("Orange Money") or _("MTN MoMo"),
            "operation": transaction.primetech_mobile_money_operation == "withdrawal" and _("Retrait") or _("Dépôt"),
            "amount": transaction.amount,
            "reason": transaction.primetech_mobile_money_reason or "",
            "served_by": transaction.primetech_mobile_money_employee_id.name or "",
        } for transaction in transactions]

    def get_closing_control_data(self):
        """Merge Mobile Money transfers into their POS payment-method total."""
        self.ensure_one()
        data = super().get_closing_control_data()
        methods_by_id = {method.id: method for method in self.payment_method_ids}
        for payment_data in data["non_cash_payment_methods"]:
            payment_method = methods_by_id.get(payment_data["id"])
            if not payment_method or payment_method.primetech_mobile_money_type not in ("orange", "momo"):
                continue
            moves = self._primetech_mobile_money_session_moves(payment_method)
            transfer_amount = sum(moves.mapped("amount"))
            opening_amount = float(
                (self.primetech_mobile_money_opening_balances or {}).get(
                    str(payment_method.id), 0.0
                )
            )
            # The displayed expected amount is the customer payments plus the
            # deposits/retraits already recorded on this wallet journal.
            # The standard closing process receives the resulting difference,
            # so only a genuine shortage/excess creates an adjustment entry.
            payment_data["amount"] += opening_amount + transfer_amount
            payment_data["number"] = max(1, payment_data["number"]) + len(moves)
            payment_data["mobile_money_provider"] = payment_method.primetech_mobile_money_type
            payment_data["mobile_money_moves"] = [
                {"name": move.payment_ref or payment_method.name, "amount": move.amount}
                for move in moves
            ]
        return data

    @api.model
    def primetech_mobile_money_opening_data(self, session_id):
        """Return the expected opening balances of configured wallets."""
        session = self.browse(session_id).exists()
        if not session or session.state != "opening_control":
            raise UserError(_("La session n'est plus en attente d'ouverture."))
        recorded_balances = session.primetech_mobile_money_opening_balances or {}
        previous_session = self.search([
            ("config_id", "=", session.config_id.id),
            ("id", "!=", session.id),
            ("state", "=", "closed"),
        ], order="stop_at desc, id desc", limit=1)
        previous_closing_balances = previous_session.primetech_mobile_money_closing_balances or {}
        wallets = []
        for payment_method in session.payment_method_ids.filtered(
            lambda method: method.primetech_mobile_money_type in ("orange", "momo")
        ):
            wallets.append({
                "id": payment_method.id,
                "name": payment_method.name,
                "amount": float(recorded_balances.get(
                    str(payment_method.id),
                    previous_closing_balances.get(
                        str(payment_method.id),
                        session._primetech_wallet_balance(payment_method),
                    ),
                )),
            })
        return wallets

    @api.model
    def primetech_save_mobile_money_closing_counts(self, session_id, wallet_amounts):
        """Keep the counted wallet totals to suggest them at the next opening."""
        session = self.browse(session_id).exists()
        if not session or session.state not in ("opened", "closing_control"):
            return False
        wallet_amounts = wallet_amounts or {}
        balances = {}
        for payment_method in session.payment_method_ids.filtered(
            lambda method: method.primetech_mobile_money_type in ("orange", "momo")
        ):
            try:
                amount = float(wallet_amounts.get(str(payment_method.id), 0.0))
            except (TypeError, ValueError):
                raise ValidationError(_("Le comptage Mobile Money est invalide."))
            if amount < 0:
                raise ValidationError(_("Le comptage Mobile Money ne peut pas être négatif."))
            balances[str(payment_method.id)] = amount
        session.primetech_mobile_money_closing_balances = balances
        return True

    @api.model
    def primetech_set_opening_control(self, session_id, cashbox_value, notes, wallet_amounts):
        """Open the POS and record each counted Mobile Money opening balance."""
        session = self.browse(session_id).exists()
        if not session or session.state != "opening_control":
            return
        wallet_amounts = wallet_amounts or {}
        wallet_values = []
        for payment_method in session.payment_method_ids.filtered(
            lambda method: method.primetech_mobile_money_type in ("orange", "momo")
        ):
            try:
                counted = float(wallet_amounts.get(str(payment_method.id), 0.0))
            except (TypeError, ValueError):
                raise ValidationError(_("Le montant d'ouverture Mobile Money est invalide."))
            if counted < 0:
                raise ValidationError(_("Le montant d'ouverture Mobile Money ne peut pas être négatif."))
            expected = session._primetech_wallet_balance(payment_method)
            difference = counted - expected
            journal = payment_method.journal_id
            if difference < 0 and not journal.loss_account_id:
                raise UserError(_("Configurez un compte de perte sur le journal %(journal)s.", journal=journal.name))
            if difference > 0 and not journal.profit_account_id:
                raise UserError(_("Configurez un compte de gain sur le journal %(journal)s.", journal=journal.name))
            wallet_values.append((payment_method, counted, difference))

        # Let Odoo open and record the physical cash control first.
        session.set_opening_control(cashbox_value, notes)
        session.primetech_mobile_money_opening_balances = {
            str(payment_method.id): counted
            for payment_method, counted, _difference in wallet_values
        }
        statement_line_model = self.env["account.bank.statement.line"]
        for payment_method, _counted, difference in wallet_values:
            if not difference:
                continue
            journal = payment_method.journal_id
            statement_line_model.create({
                "journal_id": journal.id,
                "amount": difference,
                "date": fields.Date.context_today(session),
                "payment_ref": _("Écart de comptage à l'ouverture - %(method)s", method=payment_method.name),
                "counterpart_account_id": (
                    journal.profit_account_id.id if difference > 0 else journal.loss_account_id.id
                ),
            })
        return True

    @api.model
    def primetech_mobile_money_transfer(self, session_id, payment_method_id, operation, amount, reason="", employee_id=False):
        """Transfer funds between POS cash and an Orange/MTN mobile wallet."""
        session = self.browse(session_id).exists()
        if not session or session.state != "opened":
            raise UserError(_("La session du point de vente doit être ouverte."))
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Vous n'êtes pas autorisé à effectuer des mouvements de caisse."))
        if operation not in ("withdrawal", "deposit"):
            raise ValidationError(_("Le type d'opération sélectionné est invalide."))
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            raise ValidationError(_("Le montant doit être supérieur à zéro."))

        config = session.config_id
        cash_method = config.payment_method_ids.filtered(
            lambda method: method.primetech_mobile_money_type == "cash"
        )[:1]
        payment_method = config.payment_method_ids.filtered(
            lambda method: method.id == int(payment_method_id) and method.primetech_mobile_money_type in ("orange", "momo")
        )
        if not payment_method:
            raise ValidationError(_("Le portefeuille Mobile Money sélectionné est invalide."))
        provider = payment_method.primetech_mobile_money_type
        cash_journal = cash_method.journal_id
        mobile_journal = payment_method.journal_id
        if not payment_method or not mobile_journal:
            label = _("Orange Money") if provider == "orange" else _("MTN MoMo")
            raise UserError(_("Configurez la méthode de paiement %(provider)s et son journal.", provider=label))
        if not cash_method or not cash_journal:
            raise UserError(_("Configurez une méthode de paiement de type Espèces et son journal."))
        other_method = config.payment_method_ids.filtered(
            lambda method: method.id != payment_method.id and method.journal_id == mobile_journal and method.primetech_mobile_money_type in ("orange", "momo")
        )
        if other_method:
            raise UserError(_(
                "Orange Money et MTN MoMo doivent utiliser deux journaux comptables différents. "
                "Corrigez les méthodes de paiement du point de vente avant de poursuivre."
            ))
        if cash_journal != session.cash_journal_id:
            raise UserError(_("La méthode de paiement de type Espèces doit utiliser le journal de caisse de cette session."))
        # The POS transfer account is optional: when it is not specified, the
        # cash journal suspense account is the standard clearing account.
        transfer_account = config.primetech_mobile_money_transfer_account_id or cash_journal.suspense_account_id
        if not transfer_account:
            raise UserError(_("Configurez le compte de transfert Mobile Money ou le compte d'attente du journal de caisse."))

        # A withdrawal pays out physical cash; a deposit pays out the selected
        # mobile wallet.  Check the relevant balance before posting either
        # accounting line, so a transaction can never create a negative balance.
        if operation == "withdrawal":
            cash_available = max(0.0, session.cash_register_balance_end)
            if amount > cash_available:
                raise UserError(_(
                    "Solde espèces insuffisant. Disponible : %(available).2f ; demandé : %(requested).2f.",
                    available=cash_available,
                    requested=amount,
                ))
        else:
            mobile_available = session._primetech_wallet_available_balance(payment_method)
            if amount > mobile_available:
                raise UserError(_(
                    "Solde %(provider)s insuffisant. Disponible : %(available).2f ; demandé : %(requested).2f.",
                    provider=_('Orange Money') if provider == "orange" else _('MTN MoMo'),
                    available=mobile_available,
                    requested=amount,
                ))

        employee = self.env["hr.employee"].browse(employee_id).exists()
        if not employee:
            employee = self.env.user.employee_id
        provider_label = _("Orange Money") if provider == "orange" else _("MTN MoMo")
        operation_label = _("Retrait") if operation == "withdrawal" else _("Dépôt")
        reference = _("%(operation)s %(provider)s - %(session)s", operation=operation_label, provider=provider_label, session=session.name)
        if reason:
            reference = "%s - %s" % (reference, reason.strip())

        # A withdrawal gives cash to the customer and increases the wallet;
        # a deposit does the exact opposite. Only the cash line belongs to the
        # POS session, therefore it is included in the closing cash balance.
        cash_amount = -amount if operation == "withdrawal" else amount
        mobile_amount = -cash_amount
        # POS cashiers do not need accounting write access: their authorised
        # transaction is posted server-side after the POS permission check.
        statement_line_model = self.env["account.bank.statement.line"].sudo()
        cash_line = statement_line_model.create({
            "pos_session_id": session.id,
            "journal_id": cash_journal.id,
            "amount": cash_amount,
            "date": fields.Date.context_today(session),
            "payment_ref": reference,
            "counterpart_account_id": transfer_account.id,
        })
        mobile_line = statement_line_model.create({
            "journal_id": mobile_journal.id,
            "primetech_mobile_money_session_id": session.id,
            "primetech_mobile_money_provider": provider,
            "primetech_mobile_money_operation": operation,
            "primetech_mobile_money_payment_method_id": payment_method.id,
            "primetech_mobile_money_reason": reason.strip(),
            "primetech_mobile_money_employee_id": employee.id,
            "amount": mobile_amount,
            "date": fields.Date.context_today(session),
            "payment_ref": reference,
            "counterpart_account_id": transfer_account.id,
        })
        if transfer_account.reconcile:
            clearing_lines = cash_line.move_id.line_ids.filtered(
                lambda line: line.account_id == transfer_account and not line.reconciled
            ) | mobile_line.move_id.line_ids.filtered(
                lambda line: line.account_id == transfer_account and not line.reconciled
            )
            clearing_lines.reconcile()
        # The mobile statement line is posted on the wallet journal, therefore
        # it effectively changes its balance. Flush and recompute the POS cash
        # balance before returning the updated figures to the POS interface.
        self.env.flush_all()
        session.invalidate_recordset(["cash_register_balance_end"])
        return {
            "transaction_id": mobile_line.id,
            "reference": reference,
            "provider": payment_method.name,
            "operation": operation_label,
            "amount": amount,
            "reason": reason,
            "served_by": employee.name or self.env.user.name,
            "date": fields.Datetime.to_string(fields.Datetime.now()),
            "date_time": fields.Datetime.context_timestamp(
                self, mobile_line.create_date
            ).strftime("%d/%m/%Y %H:%M:%S"),
            "balances": self.primetech_mobile_money_balances(session.id),
        }
