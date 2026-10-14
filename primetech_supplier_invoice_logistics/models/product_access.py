# -*- coding: utf-8 -*-

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError


class PrimetechLimitedProductAccess(models.AbstractModel):
    """Make product cards genuinely read-only for the limited bill role."""

    _name = "primetech.limited.product.access"
    _description = "Primetech limited product access helper"

    def _primetech_check_product_write_access(self):
        if (
            self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_user"
            )
            and not self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"
            )
        ):
            raise AccessError(_(
                "Le profil Utilisateur des factures fournisseurs logistiques "
                "peut uniquement consulter les articles."
            ))


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == "form" and self._primetech_is_limited_supplier_user():
            arch = etree.fromstring(result["arch"])
            arch.set("create", "0")
            arch.set("edit", "0")
            arch.set("delete", "0")
            result["arch"] = etree.tostring(arch, encoding="unicode")
        return result

    def _primetech_is_limited_supplier_user(self):
        return (
            self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_user"
            )
            and not self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"
            )
        )

    def write(self, vals):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().create(vals_list)

    def unlink(self):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().unlink()


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == "form" and self._primetech_is_limited_supplier_user():
            arch = etree.fromstring(result["arch"])
            arch.set("create", "0")
            arch.set("edit", "0")
            arch.set("delete", "0")
            result["arch"] = etree.tostring(arch, encoding="unicode")
        return result

    def _primetech_is_limited_supplier_user(self):
        return (
            self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_user"
            )
            and not self.env.user.has_group(
                "primetech_supplier_invoice_logistics.group_supplier_invoice_administrator"
            )
        )

    def write(self, vals):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().create(vals_list)

    def unlink(self):
        self.env["primetech.limited.product.access"]._primetech_check_product_write_access()
        return super().unlink()
