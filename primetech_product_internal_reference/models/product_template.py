# -*- coding: utf-8 -*-
"""Automatic product references and EAN-13 barcodes."""

import secrets
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    primetech_auto_internal_reference = fields.Boolean(
        string="Reference interne generee automatiquement",
        default=False,
        copy=False,
        readonly=True,
    )
    primetech_can_change_category = fields.Boolean(
        compute="_compute_primetech_can_change_category",
        string="Peut modifier la categorie",
    )

    @api.depends_context("uid")
    def _compute_primetech_can_change_category(self):
        allowed = self.env.user.has_group("stock.group_stock_manager")
        for product in self:
            product.primetech_can_change_category = allowed

    @api.model
    def _primetech_ean13_check_digit(self, value):
        """Return the EAN-13 check digit for a twelve-digit value."""
        if len(value) != 12 or not value.isdigit():
            raise ValidationError(_("La base EAN-13 doit contenir exactement douze chiffres."))
        weighted_sum = sum(
            int(digit) * (1 if position % 2 == 0 else 3)
            for position, digit in enumerate(value)
        )
        return str((10 - (weighted_sum % 10)) % 10)

    def _primetech_generate_unique_ean13(self):
        """Generate a random valid EAN-13 barcode not used by another product."""
        product_model = self.env["product.product"].sudo()
        for _attempt in range(1000):
            # The ``2`` prefix is reserved for internal variable-measure
            # barcodes. The remaining eleven digits are cryptographically
            # random, then the EAN-13 check digit is appended.
            base = "2%011d" % secrets.randbelow(10 ** 11)
            barcode = "%s%s" % (base, self._primetech_ean13_check_digit(base))
            if not product_model.search_count([("barcode", "=", barcode)]):
                return barcode
        raise ValidationError(_(
            "Impossible de reserver un code-barres EAN-13 unique. Reessayez."
        ))

    @api.model
    def primetech_generate_ean13_value(self):
        """Return an EAN-13 value for an unsaved product form."""
        return self._primetech_generate_unique_ean13()

    def action_primetech_generate_ean13(self):
        """Assign a unique and valid EAN-13 barcode to a saved product."""
        self.ensure_one()
        if self.product_variant_count != 1:
            raise ValidationError(_(
                "Generez le code-barres depuis la variante si cet article comporte des variantes."
            ))
        barcode = self.barcode or self._primetech_generate_unique_ean13()
        if not self.barcode:
            self.write({"barcode": barcode})
        return {"barcode": barcode}

    @api.model
    def _primetech_category_prefix(self, category):
        """Build a prefix from the first letter of every business category.

        Examples: AC / DELL -> AD; AC / DELL / BOX -> ADB.
        The standard Odoo root category (All) is not included.
        """
        all_category = self.env.ref("product.product_category_all", raise_if_not_found=False)
        if not category or category == all_category:
            return False

        branch = []
        current = category
        while current:
            branch.append(current)
            current = current.parent_id

        letters = []
        for current in reversed(branch):
            if current == all_category:
                continue
            # Some existing HITECH categories are stored flat, for example
            # "AC / CONNECTEURS", instead of using parent_id. Split that name
            # so every visible level still contributes its initial.
            levels = [level.strip() for level in (current.name or "").split("/")]
            for level in levels:
                if not level:
                    continue
                letter = unicodedata.normalize("NFKD", level[:1]).encode(
                    "ASCII", "ignore"
                ).decode().upper()
                if not letter or not letter.isalpha():
                    raise ValidationError(_(
                        "La categorie '%(category)s' doit commencer par une lettre.",
                        category=current.display_name,
                    ))
                letters.append(letter)
        return "".join(letters)

    @api.model
    def _primetech_next_internal_reference(self, category):
        """Reserve a unique random five-digit suffix within a category prefix."""
        prefix = self._primetech_category_prefix(category)
        if not prefix:
            return False

        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ["primetech.product.internal.reference:%s" % prefix],
        )
        for _attempt in range(1000):
            # 00000 is deliberately skipped: each generated reference has a
            # meaningful five digit suffix, for example ADB41547.
            reference = "%s%05d" % (prefix, secrets.randbelow(99999) + 1)
            self.env.cr.execute(
                "SELECT 1 FROM product_product WHERE default_code = %s LIMIT 1",
                [reference],
            )
            if not self.env.cr.fetchone():
                return reference
        raise ValidationError(_(
            "Impossible de generer une reference interne unique pour la categorie '%(category)s'.",
            category=category.display_name,
        ))

    @api.onchange("categ_id")
    def _onchange_primetech_generate_internal_reference(self):
        """Recalculate the reference immediately when the category changes."""
        for product in self:
            if not product.categ_id:
                continue
            reference = product._primetech_next_internal_reference(product.categ_id)
            product.default_code = reference or False
            product.primetech_auto_internal_reference = bool(reference)

    @api.model_create_multi
    def create(self, vals_list):
        """Generate the reference server-side for UI, imports and APIs."""
        category_model = self.env["product.category"]
        prepared_vals_list = []
        for values in vals_list:
            values = dict(values)
            category_id = values.get("categ_id")
            auto_generated = values.get("primetech_auto_internal_reference")
            if category_id and (not values.get("default_code") or auto_generated):
                reference = self._primetech_next_internal_reference(category_model.browse(category_id))
                if reference:
                    values["default_code"] = reference
                    values["primetech_auto_internal_reference"] = True
                else:
                    values.pop("default_code", None)
                    values["primetech_auto_internal_reference"] = False
            prepared_vals_list.append(values)
        return super().create(prepared_vals_list)

    def write(self, values):
        """Only inventory managers may reclassify a product."""
        if "categ_id" not in values:
            return super().write(values)
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(_(
                "Seul un administrateur Inventaire peut modifier la categorie d'un article."
            ))
        result = super().write(values)
        for product in self:
            reference = product._primetech_next_internal_reference(product.categ_id)
            super(ProductTemplate, product).write({
                "default_code": reference or False,
                "primetech_auto_internal_reference": bool(reference),
            })
        return result
