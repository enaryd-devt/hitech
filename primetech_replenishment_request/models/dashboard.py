# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReplenishmentDashboard(models.Model):
    """Virtual ORM-backed dashboard for replenishment KPIs."""

    _name = "replenishment.dashboard"
    _description = "Tableau de bord du réapprovisionnement"
    _auto = False

    name = fields.Char(default="Tableau de bord")
    total_count = fields.Integer(string="Total", compute="_compute_statistics")
    draft_count = fields.Integer(string="Brouillons", compute="_compute_statistics")
    to_approve_count = fields.Integer(string="À approuver", compute="_compute_statistics")
    approved_count = fields.Integer(string="Approuvées", compute="_compute_statistics")
    cancelled_count = fields.Integer(string="Annulées", compute="_compute_statistics")
    picking_count = fields.Integer(string="Transferts", compute="_compute_statistics")

    @api.depends_context("uid")
    def _compute_statistics(self):
        Request = self.env["replenishment.request"]
        Picking = self.env["stock.picking"]
        grouped = {item["state"]: item["state_count"] for item in Request.read_group([], ["state"], ["state"])}
        for dashboard in self:
            dashboard.total_count = Request.search_count([])
            dashboard.draft_count = grouped.get("draft", 0)
            dashboard.to_approve_count = grouped.get("to_approve", 0)
            dashboard.approved_count = grouped.get("approved", 0)
            dashboard.cancelled_count = grouped.get("cancelled", 0)
            dashboard.picking_count = Picking.search_count([("replenishment_request_id", "!=", False)])

    @api.model
    def get_statistics(self):
        record = self.new({})
        record._compute_statistics()
        return {field: record[field] for field in ["total_count", "draft_count", "to_approve_count", "approved_count", "cancelled_count", "picking_count"]}

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW replenishment_dashboard AS (
                SELECT 1 AS id, 'Tableau de bord'::varchar AS name
            )
        """)
