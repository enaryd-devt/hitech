/** @odoo-module **/

import {Component, onMounted, onWillStart, onWillUpdateProps} from "@odoo/owl";

export class ChartContainer extends Component {

    setup() {

        this.revenueChart = null;
        this.activityChart = null;

        onMounted(async () => {

            await this.loadCharts();

        });

        onWillUpdateProps(async (nextProps) => {

            console.log(
                "Charts Filters Changed",
                nextProps.filters
            );

            await this.loadCharts();

        });

    }

    async loadCharts() {

        try {

            const response = await fetch(
                "/primetech_reporting/dashboard/revenue_chart",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(
                        this.props.filters || {}
                    ),
                }
            );

            const data =
                await response.json();

            console.log(
                "CHART DATA",
                data
            );

                this.renderRevenueChart(data);

                await this.renderActivityChart();

        } catch (error) {

            console.error(
                "Erreur Graphique",
                error
            );


        }

    }

    renderRevenueChart(data) {


        const canvas =
            document.getElementById(
                "ptRevenueChart"
            );

        if (!canvas) {
            return;
        }

        if (this.revenueChart) {

            this.revenueChart.destroy();

        }

        this.revenueChart =
            new Chart(canvas, {

                type: "line",

                data: {

                    labels:
                        data.labels || [],

                    datasets: [

                        {

                            label:
                                "Chiffre d'Affaires",

                            data:
                                data.revenue || [],

                            borderColor:
                                "#0F6CBD",

                            backgroundColor:
                                "rgba(15,108,189,0.15)",

                            fill: true,

                            tension: 0.4,

                            borderWidth: 3,

                            yAxisID: "y",

                        },

                        {

                            label:
                                "Créances",

                            data:
                                data.receivables || [],

                            borderColor:
                                "#F59E0B",

                            backgroundColor:
                                "rgba(245,158,11,0.15)",

                            fill: false,

                            tension: 0.4,

                            borderWidth: 3,

                            yAxisID: "y1",

                        },

                    ],

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    interaction: {

                        mode: "index",

                        intersect: false,

                    },

                    plugins: {

                        legend: {

                            display: true,

                            position: "bottom",

                        },

                        tooltip: {

                            callbacks: {

                                label: function(context) {

                                    return (

                                        context.dataset.label +

                                        " : " +

                                        new Intl.NumberFormat(
                                            "fr-FR"
                                        ).format(
                                            context.parsed.y
                                        ) +

                                        " FCFA"

                                    );

                                },

                            },

                        },

                    },

                    scales: {

                        y: {

                            type: "linear",

                            position: "left",

                            beginAtZero: true,

                            title: {

                                display: true,

                                text:
                                    "Chiffre d'Affaires",

                            },

                        },

                        y1: {

                            type: "linear",

                            position: "right",

                            beginAtZero: true,

                            grid: {

                                drawOnChartArea: false,

                            },

                            title: {

                                display: true,

                                text:
                                    "Créances",

                            },

                        },

                    },

                },

            });


}


    async renderActivityChart() {

    const response = await fetch(
            "/primetech_reporting/dashboard/activity_chart",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json",
                },

                body: JSON.stringify(
                    this.props.filters || {}
                ),
            }
        )

    const data =
        await response.json();

    const canvas =
        document.getElementById(
            "ptActivityChart"
        );

    if (!canvas) {
        return;
    }

    if (this.activityChart) {

        this.activityChart.destroy();

    }

    this.activityChart =
        new Chart(canvas, {

            type: "doughnut",

            data: {

                labels:
                    data.labels,

                    datasets: [{

                        data: data.values,

                        backgroundColor: [

                            "#0F6CBD",
                            "#F59E0B",
                            "#22C55E",
                            "#14B8A6",

                        ],

                    }]

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

ChartContainer.template =
    "primetech_reporting_center.ChartContainer";