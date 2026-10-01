/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillUpdateProps,
} from "@odoo/owl";

export class TopProductsChart extends Component {

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

                "/primetech_reporting/dashboard/top_products_chart",

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

                "Erreur Top Produits Chart",

                error

            );

        }

    }

    renderChart(data) {

        const canvas =
            document.getElementById(
                "ptTopProductsChart"
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
                                "CA Produits",

                            data:
                                data.values || [],

                            backgroundColor: [

                                "#22C55E",
                                "#16A34A",
                                "#15803D",
                                "#4ADE80",
                                "#86EFAC",

                            ],

                            borderRadius: 10,

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

TopProductsChart.template =
    "primetech_reporting_center.TopProductsChart";