/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    useState,
    xml,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const PRESENT_STATUSES = ["present", "late", "incomplete", "extra"];

function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function shiftIsoDate(isoDate, days) {
    const date = new Date(`${isoDate}T12:00:00`);
    date.setDate(date.getDate() + days);
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Number counting up (or down) to its value with an ease-out curve.
 */
export class AnimatedNumber extends Component {
    static template = xml`<span class="o_pt_bio_number" t-esc="state.display"/>`;
    static props = {
        value: Number,
        decimals: { type: Number, optional: true },
        suffix: { type: String, optional: true },
        duration: { type: Number, optional: true },
    };

    setup() {
        this.current = 0;
        this.state = useState({ display: this.format(0) });
        onMounted(() => this.animate(this.props.value));
        onWillUpdateProps((nextProps) => {
            if (nextProps.value !== this.props.value) {
                this.animate(nextProps.value);
            }
        });
        onWillUnmount(() => cancelAnimationFrame(this.frame));
    }

    format(value) {
        const decimals = this.props.decimals || 0;
        const text = value.toLocaleString("fr-FR", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
        return this.props.suffix ? `${text}${this.props.suffix}` : text;
    }

    animate(target) {
        cancelAnimationFrame(this.frame);
        const from = this.current;
        const duration = prefersReducedMotion() ? 0 : this.props.duration || 900;
        const start = performance.now();
        const step = (now) => {
            const progress = duration ? Math.min(1, (now - start) / duration) : 1;
            const eased = 1 - Math.pow(1 - progress, 3);
            this.current = progress < 1 ? from + (target - from) * eased : target;
            this.state.display = this.format(this.current);
            if (progress < 1) {
                this.frame = requestAnimationFrame(step);
            }
        };
        this.frame = requestAnimationFrame(step);
    }
}

export class BiometricDashboard extends Component {
    static template = "primetech_biometric_attendance.Dashboard";
    static components = { AnimatedNumber };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            data: null,
            date: false,
            loading: true,
            refreshing: false,
            busyAction: false,
            renderKey: 0,
        });
        onWillStart(() => this.load());
        this.timer = setInterval(() => {
            if (this.state.data && this.state.data.is_today && !this.state.refreshing) {
                this.load(true);
            }
        }, 60000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            const previousDate = this.state.data && this.state.data.date;
            this.state.data = await this.orm.call(
                "biometric.attendance.day", "get_dashboard_data", [this.state.date || false]
            );
            this.state.date = this.state.data.date;
            if (previousDate !== this.state.data.date) {
                // Replay the entrance animations when another day is displayed.
                this.state.renderKey++;
            }
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        this.state.refreshing = true;
        try {
            this.state.data = await this.orm.call(
                "biometric.attendance.day", "action_dashboard_refresh", [this.state.date || false]
            );
            const failing = this.state.data.devices.filter((device) => device.state === "error");
            if (failing.length) {
                this.notification.add(
                    _t("Pointeuse injoignable : %s", failing.map((device) => device.name).join(", ")),
                    { type: "danger" }
                );
            } else {
                this.notification.add(_t("Pointages synchronisés et présences recalculées."), {
                    type: "success",
                });
            }
        } finally {
            this.state.refreshing = false;
        }
    }

    shiftDate(days) {
        if (days > 0 && this.state.data.is_today) {
            return;
        }
        this.state.date = shiftIsoDate(this.state.date, days);
        this.load();
    }

    goToday() {
        this.state.date = false;
        this.load();
    }

    onDateChange(ev) {
        if (ev.target.value) {
            this.state.date = ev.target.value;
            this.load();
        }
    }

    // ------------------------------------------------------------------
    // Quick actions
    // ------------------------------------------------------------------
    get quickActions() {
        const data = this.state.data;
        const counters = data.counters;
        const actions = [
            {
                key: "punch",
                label: _t("Pointer"),
                description: _t("Ajouter un pointage oublié"),
                icon: "fa-hand-pointer-o",
                tone: "success",
            },
            {
                key: "to_fix",
                label: _t("À corriger"),
                description: _t("Pointages à corriger : entrées / sorties manquantes du mois"),
                icon: "fa-wrench",
                tone: "warning",
                badge: counters.to_fix,
            },
            {
                key: "absences",
                label: _t("Absences"),
                description: _t("Justifier les absences non justifiées du mois"),
                icon: "fa-check-square-o",
                tone: "danger",
                badge: counters.unjustified_absences,
            },
            {
                key: "report",
                label: _t("Rapport"),
                description: _t("Rapport de présence PDF par période et par employé"),
                icon: "fa-file-pdf-o",
                tone: "info",
            },
            {
                key: "recompute",
                label: _t("Recalculer"),
                description: _t("Réanalyser une période"),
                icon: "fa-calculator",
                tone: "secondary",
            },
        ];
        if (data.is_manager) {
            actions.push(
                {
                    key: "schedules",
                    label: _t("Horaires"),
                    description: counters.schedules
                        ? _t("Horaires de pointage : %s configuré(s)", counters.schedules)
                        : _t("Horaires de pointage : aucun horaire, à configurer"),
                    icon: "fa-clock-o",
                    tone: counters.schedules ? "secondary" : "warning",
                    badge: counters.schedules ? 0 : "!",
                },
                {
                    key: "import_users",
                    label: _t("Utilisateurs"),
                    description: counters.unmapped_users
                        ? _t("Importer les utilisateurs : %s identifiant(s) sans employé", counters.unmapped_users)
                        : _t("Importer les utilisateurs des pointeuses"),
                    icon: "fa-users",
                    tone: "primary",
                    badge: counters.unmapped_users,
                },
                {
                    key: "devices",
                    label: _t("Pointeuses"),
                    description: _t("Connexion, heure, maintenance"),
                    icon: "fa-server",
                    tone: "secondary",
                },
                {
                    key: "settings",
                    label: _t("Paramètres"),
                    description: _t("Règles de pointage de la société"),
                    icon: "fa-cog",
                    tone: "secondary",
                }
            );
        }
        return actions;
    }

    async runQuickAction(quickAction) {
        if (this.state.busyAction) {
            return;
        }
        const reload = { onClose: () => this.load(true) };
        const month = this.state.date.slice(0, 8);
        this.state.busyAction = quickAction.key;
        try {
            switch (quickAction.key) {
                case "punch":
                    await this.action.doAction(
                        "primetech_biometric_attendance.zk_machine_attendance_manual_action", reload
                    );
                    break;
                case "to_fix":
                    this.openDays(_t("Pointages à corriger"), [
                        ["date", ">=", `${month}01`],
                        ["justified", "=", false],
                        "|", "|",
                        ["missing_check_in", "=", true],
                        ["missing_check_out", "=", true],
                        ["outside_window", "=", true],
                    ]);
                    break;
                case "absences":
                    this.openKpi("month_absent");
                    break;
                case "report":
                    await this.action.doAction(
                        "primetech_biometric_attendance.biometric_attendance_report_wizard_action"
                    );
                    break;
                case "recompute":
                    await this.action.doAction(
                        "primetech_biometric_attendance.biometric_attendance_recompute_wizard_action",
                        reload
                    );
                    break;
                case "schedules":
                    await this.action.doAction(
                        "primetech_biometric_attendance.biometric_attendance_schedule_action"
                    );
                    break;
                case "import_users":
                    await this.importUsers();
                    break;
                case "devices":
                    await this.action.doAction(
                        "primetech_biometric_attendance.biometric_device_details_action"
                    );
                    break;
                case "settings":
                    await this.action.doAction("hr_attendance.action_hr_attendance_settings");
                    break;
            }
        } finally {
            this.state.busyAction = false;
        }
    }

    async importUsers() {
        const deviceIds = this.state.data.devices.map((device) => device.id);
        if (!deviceIds.length) {
            await this.action.doAction("primetech_biometric_attendance.biometric_device_details_action");
            return;
        }
        const action = await this.orm.call("biometric.device.details", "action_import_users", [deviceIds]);
        await this.action.doAction(action);
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    openDays(name, domain, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "biometric.attendance.day",
            views: [[false, "list"], [false, "form"]],
            domain,
            context,
        });
    }

    openKpi(kind) {
        const date = this.state.date;
        const dayDomain = [["date", "=", date]];
        const config = {
            expected: [_t("Effectif attendu"), [...dayDomain, ["plan_source", "!=", "none"]]],
            present: [_t("Présents"), [...dayDomain, ["status", "in", PRESENT_STATUSES]]],
            late: [_t("Retards"), [...dayDomain, ["is_late", "=", true]]],
            absent: [_t("Absents"), [...dayDomain, ["status", "=", "absent"]]],
            pending: [_t("Pas encore arrivés"), [...dayDomain, ["status", "=", "pending"]]],
            leave: [_t("Congés et jours fériés"), [...dayDomain, ["status", "in", ["leave", "holiday"]]]],
            incomplete: [_t("Pointages incomplets"), [...dayDomain, ["status", "=", "incomplete"]]],
            month_late: [
                _t("Retards du mois"),
                [["date", ">=", `${date.slice(0, 8)}01`], ["date", "<=", date], ["is_late", "=", true]],
            ],
            month_absent: [
                _t("Absences non justifiées du mois"),
                [
                    ["date", ">=", `${date.slice(0, 8)}01`],
                    ["date", "<=", date],
                    ["status", "=", "absent"],
                    ["justified", "=", false],
                ],
            ],
        }[kind];
        this.openDays(...config);
    }

    openTrendDay(day) {
        this.openDays(_t("Présences du %s", day.label), [["date", "=", day.date]]);
    }

    openDepartment(department) {
        this.openDays(_t("Présences - %s", department.name), [
            ["date", "=", this.state.date],
            ["department_id", "=", department.department_id || false],
        ]);
    }

    openEmployeeLate(row) {
        const date = this.state.date;
        this.openDays(_t("Retards de %s", row.name), [
            ["employee_id", "=", row.employee_id],
            ["date", ">=", `${date.slice(0, 8)}01`],
            ["date", "<=", date],
            ["is_late", "=", true],
        ]);
    }

    openDay(row) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "biometric.attendance.day",
                res_id: row.id,
                views: [[false, "form"]],
            }
        );
    }

    openDevice(device) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "biometric.device.details",
            res_id: device.id,
            views: [[false, "form"]],
        });
    }

    openAction(xmlId) {
        this.action.doAction(xmlId);
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------
    formatMinutes(minutes) {
        if (!minutes) {
            return "0 min";
        }
        const hours = Math.floor(minutes / 60);
        const rest = minutes % 60;
        return hours ? `${hours} h ${String(rest).padStart(2, "0")}` : `${rest} min`;
    }

    /** Staggered entrance delay, in milliseconds. */
    delay(index, step = 60, base = 0) {
        return `animation-delay: ${base + index * step}ms;`;
    }

    get trendMax() {
        const totals = this.state.data.trend.map(
            (day) => day.present + day.late + day.absent + day.leave
        );
        return Math.max(1, ...totals);
    }

    barStyle(value) {
        return `height: ${(100 * value) / this.trendMax}%;`;
    }

    columnStyle(index) {
        return `animation-delay: ${200 + index * 45}ms;`;
    }

    departmentRate(department) {
        return department.expected ? Math.round((100 * department.present) / department.expected) : 0;
    }
}

registry.category("actions").add("primetech_biometric_attendance.dashboard", BiometricDashboard);
