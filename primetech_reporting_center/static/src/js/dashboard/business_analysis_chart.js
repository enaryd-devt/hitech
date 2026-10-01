/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillUpdateProps,
} from "@odoo/owl";

export class BusinessAnalysisChart extends Component {

    setup() {

        this.chart = null;

        onMounted(async () => {

            await this.loadChart();

        });

        onWillUpdateProps(async () => {

            await this.loadChart();

        });

    }

    async loadChart() {

        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/business_analysis",

                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                    },

                    body: JSON.stringify(

                        this.props.filters || {}

                    ),

                }

            );

            const data =
                await response.json();

            console.log(
                "Business Analysis",
                data
            );

            this.renderChart(data);

        } catch (error) {

            console.error(

                "Erreur analyse financière",

                error

            );

        }

    }

    renderChart(data) {

        const canvas =
            document.getElementById(
                "ptBusinessAnalysisChart"
            );

        if (!canvas) {
            return;
        }

        if (this.chart) {

            this.chart.destroy();

        }

        this.chart =
            new Chart(canvas, {

                type: "doughnut",

                data: {

                    labels:
                        data.labels || [],

                    datasets: [

                        {

                            data:
                                data.values || [],

                            backgroundColor: [

                                "#0F6CBD",
                                "#22C55E",
                                "#F59E0B",
                                "#8B5CF6",

                            ],

                            borderWidth: 0,

                        },

                    ],

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {

                            position:
                                "bottom",

                        },

                    },

                },

            });

    }

}

BusinessAnalysisChart.template =
    "primetech_reporting_center.BusinessAnalysisChart";