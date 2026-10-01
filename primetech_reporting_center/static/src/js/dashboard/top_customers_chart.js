/** @odoo-module **/

import {
    Component,
    useState,
    onMounted,
    onWillUpdateProps,
} from "@odoo/owl";

export class TopCustomersChart extends Component {

    setup() {

        this.chart = null;

        onMounted(async () => {

            await this.loadChart();

        });
        this.state = useState({

            loading: true,

        });


        onWillUpdateProps(async () => {

            await this.loadChart();

        });

    }

    async loadChart() {

        this.state.loading = true;


        try {

            const response = await fetch(

                "/primetech_reporting/dashboard/top_customers_chart",

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

                "Erreur Top Clients Chart",

                error

            );

        }
        finally {

            this.state.loading = false;

        }

    }

    renderChart(data) {

        const canvas =
            document.getElementById(
                "ptTopCustomersChart"
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
                                "CA Clients",

                            data:
                                data.values || [],

                            backgroundColor: [

                                "#0F6CBD",
                                "#1D4ED8",
                                "#2563EB",
                                "#3B82F6",
                                "#60A5FA",

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

TopCustomersChart.template =
    "primetech_reporting_center.TopCustomersChart";