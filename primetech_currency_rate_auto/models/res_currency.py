# -*- coding: utf-8 -*-
"""Daily international exchange-rate import for Odoo currencies."""

import logging
import json
import ssl
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    import certifi
except ImportError:  # pragma: no cover - standard SSL store remains the fallback
    certifi = None

_logger = logging.getLogger(__name__)
_ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_OPEN_ER_API_URL = "https://open.er-api.com/v6/latest/EUR"
_ECB_NAMESPACE = {"gesmes": "http://www.gesmes.org/xml/2002-08-01", "def": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

# The CFA franc is permanently pegged to the euro.  ECB does not publish it
# in its daily XML, so it is safely completed from the official fixed parity.
_EUR_FIXED_RATES = {"EUR": 1.0, "XAF": 655.957, "XOF": 655.957}


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _primetech_ssl_context(self):
        return ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()

    @api.model
    def _primetech_fetch_ecb_daily_rates(self):
        """Return the official ECB daily rates expressed as 1 EUR = currency."""
        try:
            request = Request(_ECB_DAILY_URL, headers={"User-Agent": "Odoo Primetech Currency Updater/1.0"})
            # Some Windows Odoo distributions do not expose the system CA
            # bundle to Python.  certifi supplies a maintained CA bundle while
            # preserving strict certificate verification.
            with urlopen(request, timeout=20, context=self._primetech_ssl_context()) as response:  # nosec B310: trusted official endpoint
                payload = response.read()
            root = ElementTree.fromstring(payload)
        except Exception as error:
            raise UserError(_("Impossible de récupérer les taux internationaux : %s") % error) from error

        rates = dict(_EUR_FIXED_RATES)
        rate_date = False
        for cube in root.findall(".//def:Cube", _ECB_NAMESPACE):
            if cube.get("time"):
                rate_date = cube.get("time")
            currency, rate = cube.get("currency"), cube.get("rate")
            if currency and rate:
                try:
                    rates[currency] = float(rate)
                except ValueError:
                    _logger.warning("Invalid ECB rate for %s: %s", currency, rate)
        if not rate_date or len(rates) <= len(_EUR_FIXED_RATES):
            raise UserError(_("La source internationale n'a retourné aucun taux exploitable."))
        return fields.Date.to_date(rate_date), rates

    @api.model
    def _primetech_fetch_supplementary_rates(self):
        """Fetch a broad international EUR rate set for non-ECB currencies."""
        try:
            request = Request(_OPEN_ER_API_URL, headers={"User-Agent": "Odoo Primetech Currency Updater/1.0"})
            with urlopen(request, timeout=20, context=self._primetech_ssl_context()) as response:  # nosec B310: documented public rate endpoint
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("result") != "success" or not isinstance(payload.get("rates"), dict):
                raise ValueError("Réponse de taux invalide")
            return {
                code: float(value)
                for code, value in payload["rates"].items()
                if isinstance(code, str) and isinstance(value, (int, float)) and value > 0
            }
        except Exception as error:
            _logger.warning("Primetech supplementary currency source unavailable: %s", error)
            return {}

    @api.model
    def _primetech_update_international_rates(self):
        """Create or update global ``res.currency.rate`` entries for active currencies."""
        active_currencies = self.with_context(active_test=False).search([("active", "=", True)])
        rate_date, rates = self._primetech_fetch_ecb_daily_rates()
        missing_codes = set(active_currencies.mapped("name")) - set(rates)
        if missing_codes:
            # ECB does not list every international currency (for example NGN).
            # Complete only the missing codes, while keeping ECB and the CFA
            # fixed parity as the preferred sources whenever available.
            supplementary_rates = self._primetech_fetch_supplementary_rates()
            rates.update({code: rate for code, rate in supplementary_rates.items() if code in missing_codes})
            rates.update(_EUR_FIXED_RATES)
        currencies = active_currencies.filtered(lambda currency: currency.name in rates)
        if not currencies:
            raise UserError(_("Aucune devise active ne correspond aux taux internationaux disponibles."))

        Rate = self.env["res.currency.rate"]
        updated = 0
        for currency in currencies:
            values = {"name": rate_date, "rate": rates[currency.name], "company_id": False}
            existing = Rate.search([
                ("currency_id", "=", currency.id), ("company_id", "=", False), ("name", "=", rate_date),
            ], limit=1)
            if existing:
                existing.write(values)
            else:
                values["currency_id"] = currency.id
                Rate.create(values)
            updated += 1
        _logger.info("Primetech: %s currency rate(s) updated for %s from ECB", updated, rate_date)
        skipped = sorted(set(active_currencies.mapped("name")) - set(rates))
        if skipped:
            _logger.warning("Primetech: no international rate available for active currencies: %s", ", ".join(skipped))
        return {"date": rate_date, "updated": updated, "skipped": skipped}

    @api.model
    def _cron_primetech_update_currency_rates(self):
        """Daily cron entry point; failures are logged so the next run retries."""
        if self.env["ir.config_parameter"].sudo().get_param("primetech_currency_rate_auto.enabled", "True") != "True":
            return False
        try:
            return self._primetech_update_international_rates()
        except Exception:
            _logger.exception("Primetech currency-rate update failed")
            return False
