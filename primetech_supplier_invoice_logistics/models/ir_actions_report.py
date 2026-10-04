# -*- coding: utf-8 -*-

from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _get_layout(self):
        # Odoo appelle aussi cette méthode sur un recordset vide pendant la
        # préparation wkhtmltopdf : ne jamais imposer un singleton ici.
        if len(self) == 1 and self.report_name == "primetech_supplier_invoice_logistics.report_primetech_payment_receipt":
            return self.env.ref(
                "primetech_supplier_invoice_logistics.report_payment_receipt_minimal_layout"
            )
        return super()._get_layout()
