# -*- coding: utf-8 -*-
"""Shared, validated date ranges for the overview dashboards."""
from datetime import timedelta

from odoo import fields


class DashboardDateRange:
    """Build the current and comparison ranges used by dashboard services."""

    PERIODS = {"today", "week", "month", "quarter", "year", "custom"}

    @classmethod
    def _to_date(cls, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            return False

    @classmethod
    def resolve(cls, filters=None, today=None, default_period="month"):
        """Return a normalized ``(period, start, end)`` tuple.

        Custom ranges fall back to the current month when one of their dates is
        missing or invalid.  This keeps RPC calls safe even if a browser request
        is crafted outside the dashboard UI.
        """
        filters = filters or {}
        today = today or fields.Date.today()
        period = filters.get("period") or default_period
        if period not in cls.PERIODS:
            period = default_period

        if period == "custom":
            start = cls._to_date(filters.get("date_from")) or today.replace(day=1)
            end = cls._to_date(filters.get("date_to")) or today
            if start > end:
                start, end = end, start
            return period, start, end

        starts = {
            "today": today,
            "week": today - timedelta(days=today.weekday()),
            "month": today.replace(day=1),
            "quarter": today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1),
            "year": today.replace(month=1, day=1),
        }
        return period, starts.get(period, starts[default_period]), today

    @staticmethod
    def previous_bounds(start, end):
        """Return the preceding range with the exact same inclusive duration."""
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=(end - start).days)
        return previous_start, previous_end
