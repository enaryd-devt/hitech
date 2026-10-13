from odoo import api, models


class ReportingHome(models.AbstractModel):
    _name = "primetech.reporting.home"
    _description = "Reporting quick actions"

    @api.model
    def get_quick_actions(self):
        """Only return actions belonging to one of the user's reporting roles."""
        actions = (
            ("group_reporting_accounting", "Balance générale", "Préparer et imprimer la balance", "action_trial_balance_wizard", "fa-calculator"),
            ("group_reporting_accounting", "Grand livre", "Préparer et imprimer le grand livre", "action_general_ledger_wizard", "fa-book"),
            ("group_reporting_sales", "Rapport périodique des ventes", "Préparer et imprimer le rapport", "action_sales_periodic_report", "fa-line-chart"),
            ("group_reporting_sales", "Analyse clients", "Préparer et imprimer l'analyse", "action_sales_customer_analysis_report", "fa-users"),
            ("group_reporting_sales", "Analyse produits", "Préparer et imprimer l'analyse", "action_sales_product_analysis_report", "fa-cubes"),
            ("group_reporting_purchase", "Analyse des achats", "Préparer et imprimer le rapport", "action_purchase_analysis_report", "fa-shopping-cart"),
            ("group_reporting_purchase", "Achats par fournisseur", "Préparer et imprimer le rapport", "action_purchase_supplier_report", "fa-truck"),
            ("group_reporting_stock", "État du stock", "Préparer et imprimer l'état", "action_stock_status_wizard", "fa-cubes"),
            ("group_reporting_stock", "Mouvements de stock", "Préparer et imprimer le rapport", "action_stock_movement_wizard", "fa-exchange"),
            ("group_reporting_stock", "Produits déstockés / livrés", "Préparer et imprimer les livraisons", "action_stock_delivery_wizard", "fa-sign-out"),
            ("group_reporting_hr", "Effectif", "Préparer et imprimer le rapport RH", "action_hr_headcount_report", "fa-users"),
            ("group_reporting_hr", "Présences", "Préparer et imprimer le rapport RH", "action_hr_attendance_report", "fa-clock-o"),
        )
        result = []
        for group, title, description, action_xmlid, icon in actions:
            if self.env.user.has_group("primetech_reporting_center.%s" % group):
                action = self.env.ref("primetech_reporting_center.%s" % action_xmlid, raise_if_not_found=False)
                if action:
                    result.append({"id": action.id, "title": title, "description": description, "icon": icon})
        return result
