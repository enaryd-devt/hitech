from odoo import models


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def primetech_update_payment_receipt_template(self):
        """Connect the installed custom payment receipt to frozen values.

        This database-specific receipt is a sibling QWeb extension, therefore
        a normal XML inheritance cannot reliably target its inner elements.
        """
        base_view = self.env.ref("account.report_payment_receipt_document")
        views = self.search([
            ("inherit_id", "=", base_view.id),
            ("arch_db", "ilike", "Solde actuel"),
        ])
        old_before = "-((o.partner_id.credit - o.partner_id.debit) + (o.amount if isinstance(o.amount, (float,int)) else 0.0))"
        old_after = "-(o.partner_id.credit - o.partner_id.debit)"
        for view in views:
            arch = view.with_context(lang="en_US").arch_db
            new_arch = arch.replace(old_before, "o._get_partner_receipt_balance_values()['before_amount']")
            new_arch = new_arch.replace(old_after, "o._get_partner_receipt_balance_values()['after_amount']")
            new_arch = new_arch.replace("Solde actuel", "Solde \u00e0 date")
            new_arch = new_arch.replace("Solde a date", "Solde \u00e0 date")
            if new_arch != arch:
                view.with_context(lang="en_US").write({"arch_db": new_arch})
        return True
