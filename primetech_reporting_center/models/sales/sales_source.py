from datetime import datetime, time, timedelta

from odoo import api, models


class SalesSource(models.AbstractModel):
    """Unified, de-duplicated source for reports based on completed sales."""

    _name = "primetech.sales.source"
    _description = "Reporting sales source"

    @api.model
    def _primetech_sales_lines(self, date_from, date_to, company_id=False, user_id=False, partner_id=False):
        invoice_domain = [
            ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
            ("invoice_date", ">=", date_from), ("invoice_date", "<=", date_to),
        ]
        if "pos_order_ids" in self.env["account.move"]._fields:
            # A POS invoice represents a ticket already reported below.
            invoice_domain.append(("pos_order_ids", "=", False))
        pos_domain = [
            ("state", "in", ["paid", "done", "invoiced"]),
            ("date_order", ">=", datetime.combine(date_from, time.min)),
            ("date_order", "<", datetime.combine(date_to + timedelta(days=1), time.min)),
        ]
        for field, value in (("company_id", company_id), ("invoice_user_id", user_id), ("partner_id", partner_id)):
            if value:
                invoice_domain.append((field, "=", value))
        for field, value in (("company_id", company_id), ("user_id", user_id), ("partner_id", partner_id)):
            if value:
                pos_domain.append((field, "=", value))

        result = []
        for invoice in self.env["account.move"].search(invoice_domain):
            for line in invoice.invoice_line_ids.filtered(lambda l: l.product_id and not l.display_type):
                result.append({"document": invoice.name, "date": invoice.invoice_date, "customer": invoice.partner_id,
                               "seller": invoice.invoice_user_id, "product": line.product_id, "qty": line.quantity,
                               "unit_price": line.price_unit, "ht": line.price_subtotal, "ttc": line.price_total,
                               "cost": self._primetech_invoice_line_cost(line), "source": "invoice"})
        for order in self.env["pos.order"].search(pos_domain):
            for line in order.lines.filtered("product_id"):
                result.append({"document": order.name, "date": order.date_order.date(), "customer": order.partner_id,
                               "seller": order.user_id, "product": line.product_id, "qty": line.qty,
                               "unit_price": line.price_unit, "ht": line.price_subtotal,
                               "ttc": line.price_subtotal_incl, "cost": self._primetech_pos_line_cost(line),
                               "source": "pos"})
        return result

    @api.model
    def _primetech_invoice_line_cost(self, line):
        """Cost of an invoiced line, in company currency.

        Uses the cost frozen on the sale order line when sale_margin is
        installed, otherwise the product standard cost.
        """
        product = line.product_id
        qty = line.product_uom_id._compute_quantity(line.quantity, product.uom_id) if line.product_uom_id else line.quantity
        sale_lines = line.sale_line_ids if "sale_line_ids" in line._fields else []
        sale_line = sale_lines[:1] if sale_lines else False
        if sale_line and "purchase_price" in sale_line._fields and sale_line.purchase_price:
            # purchase_price is expressed in the sale line UoM.
            return sale_line.purchase_price * line.quantity
        return qty * product.with_company(line.company_id).standard_price

    @api.model
    def _primetech_pos_line_cost(self, line):
        """Cost of a POS line: the cost recorded on the ticket when available."""
        if "total_cost" in line._fields and (
            "is_total_cost_computed" not in line._fields or line.is_total_cost_computed
        ):
            return line.total_cost
        return line.qty * line.product_id.with_company(line.company_id).standard_price
