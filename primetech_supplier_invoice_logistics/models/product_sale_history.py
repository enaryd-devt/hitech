# -*- coding: utf-8 -*-

from odoo import fields, models, tools


class PrimetechProductSaleHistory(models.Model):
    """Unified, read-only product sales history for invoices and POS orders."""

    _name = "primetech.product.sale.history"
    _description = "Historique unifié des ventes article"
    _auto = False
    _order = "date desc, id desc"

    source = fields.Selection([
        ("invoice", "Facture client"),
        ("pos", "Point de Vente"),
    ], string="Source", readonly=True)
    product_tmpl_id = fields.Many2one("product.template", string="Article", readonly=True)
    product_id = fields.Many2one("product.product", string="Variante", readonly=True)
    invoice_id = fields.Many2one("account.move", string="Facture client", readonly=True)
    pos_order_id = fields.Many2one("pos.order", string="Commande PdV", readonly=True)
    reference = fields.Char(string="Référence", readonly=True)
    date = fields.Datetime(string="Date", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Client", readonly=True)
    quantity = fields.Float(string="Qté commandée", readonly=True)
    quantity_delivered = fields.Float(string="Qté livrée", readonly=True)
    price_unit = fields.Monetary(string="Prix unitaire", readonly=True)
    subtotal = fields.Monetary(string="Total", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Devise", readonly=True)
    company_id = fields.Many2one("res.company", string="Société", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW primetech_product_sale_history AS (
                SELECT
                    aml.id AS id,
                    'invoice'::varchar AS source,
                    pp.product_tmpl_id AS product_tmpl_id,
                    aml.product_id AS product_id,
                    aml.move_id AS invoice_id,
                    NULL::integer AS pos_order_id,
                    am.name AS reference,
                    aml.date AS date,
                    aml.partner_id AS partner_id,
                    aml.quantity AS quantity,
                    aml.quantity AS quantity_delivered,
                    aml.price_unit AS price_unit,
                    aml.price_subtotal AS subtotal,
                    aml.currency_id AS currency_id,
                    aml.company_id AS company_id
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN product_product pp ON pp.id = aml.product_id
                WHERE am.move_type = 'out_invoice' AND am.state = 'posted'

                UNION ALL

                SELECT
                    1000000000 + pol.id AS id,
                    'pos'::varchar AS source,
                    pp.product_tmpl_id AS product_tmpl_id,
                    pol.product_id AS product_id,
                    NULL::integer AS invoice_id,
                    po.id AS pos_order_id,
                    po.name AS reference,
                    po.date_order AS date,
                    po.partner_id AS partner_id,
                    pol.qty AS quantity,
                    pol.qty AS quantity_delivered,
                    pol.price_unit AS price_unit,
                    pol.price_subtotal AS subtotal,
                    rc.currency_id AS currency_id,
                    po.company_id AS company_id
                FROM pos_order_line pol
                JOIN pos_order po ON po.id = pol.order_id
                JOIN product_product pp ON pp.id = pol.product_id
                JOIN res_company rc ON rc.id = po.company_id
                WHERE po.state IN ('paid', 'done', 'invoiced')
                  AND po.account_move IS NULL
            )
        """)
