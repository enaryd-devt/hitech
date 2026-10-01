/** @odoo-module **/

import {
    Component,
    useState,
    onMounted,
    onWillUpdateProps,
} from "@odoo/owl";

export class TopSalespersonsChart extends Component {

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

                "/primetech_reporting/dashboard/top_salespersons_chart",

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

        } catch (error) {

            console.error(

                "Erreur Top Commerciaux Chart",

                error

            );

        }

    }

    renderChart(data) {

        const canvas =
            document.getElementById(
                "ptTopSalespersonsChart"
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
                        data.labels || [],

                    datasets: [

                        {

                            label:
                                "CA Commercial",

                            data:
                                data.values || [],

                            borderRadius: 10,

                            backgroundColor: [

                                "#F59E0B",
                                "#D97706",
                                "#FBBF24",
                                "#FCD34D",
                                "#FDE68A",

                            ],

                        },

                    ],

                },

                options: {

                    indexAxis: "y",

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

TopSalespersonsChart.template =
    "primetech_reporting_center.TopSalespersonsChart";