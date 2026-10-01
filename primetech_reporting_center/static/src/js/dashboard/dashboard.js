/** @odoo-module **/

import {
    Component,
    useState,
    onMounted,
    onWillUnmount,
} from "@odoo/owl";

import { registry } from "@web/core/registry";


import { PrimetechKPICards } from "./kpi_cards";
import { ChartContainer } from "./charts";
import { RecentActivities } from "./recent_activities";
import { FavoriteReports } from "./favorite_reports";
import { QuickActions } from "./quick_actions";
import { ExecutiveOverview } from "./executive_overview";
import { TopCustomers } from "./top_customers";
import { TopProducts } from "./top_products";
import { RiskCenter } from "./risk_center";
import { AlertsPanel } from "./alerts_panel";
import { TopSalespersons } from "./top_salespersons";
import { BusinessAnalysisChart  } from "./business_analysis_chart";
import { MarginAnalysisChart } from "./margin_analysis_chart";
import { TopCustomersChart } from "./top_customers_chart";
import { TopProductsChart } from "./top_products_chart";
import { TopSalespersonsChart } from "./top_salespersons_chart";
import { Champions } from "./champions";
import { TargetsProgress } from "./targets_progress";
import { SalesForecast } from "./sales_forecast";
import { SmartAlerts } from "./smart_alerts";
import { ExecutiveDetails } from "./executive_details";
import { ExecutiveBoard } from "./executive_board";

export class PrimetechReportingDashboard extends Component {

    static props = { "*": true };


static template =
    "primetech_reporting_center.Dashboard";

static components = {



    SmartAlerts,
    SalesForecast,
    TargetsProgress,
    Champions,
    TopCustomersChart,
    TopSalespersonsChart,
    TopProductsChart,
    MarginAnalysisChart,
    BusinessAnalysisChart ,
    TopSalespersons,
    AlertsPanel,
    PrimetechKPICards,
    ChartContainer,
    RecentActivities,
    FavoriteReports,
    QuickActions,
    ExecutiveOverview,
    ExecutiveDetails,
    ExecutiveBoard,
    TopCustomers,
    TopProducts,
    RiskCenter,

};

setup() {

    const savedState = JSON.parse(

        sessionStorage.getItem(
            "primetech_dashboard_state"
        ) || "{}"

    );

    this.state = useState({

        refreshKey: 0,

        lastRefresh:
            new Date().toLocaleString(
                "fr-FR"
            ),

        filters:

            savedState.filters || {

                period: "month",

                dateFrom: null,

                dateTo: null,

                companyId: null,

            },

    });


    this.refreshInterval =
        setInterval(() => {

            this.state.refreshKey++;

            this.state.lastRefresh =
                new Date().toLocaleString(
                    "fr-FR"
                );

        }, 60000);

        onMounted(() => {

            if (savedState.scrollY) {

                setTimeout(() => {

                    window.scrollTo({

                        top: savedState.scrollY,

                        behavior: "instant",

                    });

                }, 300);

            }

        });

        onWillUnmount(() => {

            sessionStorage.setItem(

                "primetech_dashboard_state",

                JSON.stringify({

                    filters:
                        this.state.filters,

                    scrollY:
                        window.scrollY,

                })

            );

            clearInterval(
                this.refreshInterval
            );

        });


    }



    updateFilters(filters) {

        this.state.filters = {

            ...this.state.filters,

            ...filters,

        };

        this.state.refreshKey++;

        this.state.lastRefresh =
            new Date().toLocaleString(
                "fr-FR"
            );

        console.log(

            "Dashboard Filters",

            this.state.filters

        );

    }

}

registry.category("actions").add(

"primetech_reporting_dashboard",

PrimetechReportingDashboard

);
