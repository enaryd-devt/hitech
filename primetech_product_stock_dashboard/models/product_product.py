# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import AccessError


class ProductProduct(models.Model):
    _inherit = "product.product"

    def check_access_rights(self, operation, raise_exception=True):
        """Apply the article-management right to variants too."""
        if (
            operation in ("create", "write", "unlink")
            and not self.env.is_superuser()
            and not self.env.user.has_group("product.group_product_manager")
            and not self.env.user.has_group("stock.group_stock_manager")
        ):
            if raise_exception:
                raise AccessError(_(
                    "Vous avez un accès en lecture seule aux articles. "
                    "Activez le droit de création d'article sur votre utilisateur "
                    "pour pouvoir les créer ou les modifier."
                ))
            return False
        return super().check_access_rights(operation, raise_exception=raise_exception)
