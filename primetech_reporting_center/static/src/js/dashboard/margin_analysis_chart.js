/** @odoo-module **/

import {
    Component,
    useState,
    onMounted,
    onWillUpdateProps,
} from "@odoo/owl";

export class MarginAnalysisChart extends Component {

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

        const response = await fetch(

            "/primetech_reporting/dashboard/margin_analysis",

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

        this.renderChart(data);

    }

    renderChart(data) {

        const canvas =
            document.getElementById(
                "ptMarginAnalysisChart"
            );

        if (!canvas) {
            return;
        }

        if (this.chart) {

            this.chart.destroy();

        }

        this.chart =
            new Chart(canvas, {

                type: "bar",

                data: {

                    labels:
                        data.labels,

                    datasets: [

                        {

                            data:
                                data.values,

                            borderRadius: 10,

                        },

                    ],

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {

                            display: false,

                        },

                    },

                },

            });

    }

}

MarginAnalysisChart.template =
    "primetech_reporting_center.MarginAnalysisChart";