/** @odoo-module **/
/**
 * Automatic refresh while a backup / test copy is running.
 *
 * As long as the displayed record is running, its state is checked every few
 * seconds with a light read. As soon as the execution is over, the view is
 * reloaded: the status, the spinner and the journal update by themselves,
 * without changing view.
 */
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { BadgeField, badgeField } from "@web/views/fields/badge/badge_field";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, useEffect } from "@odoo/owl";

const POLL_DELAY = 3000;
const RUNNING = "running";

/**
 * @param {() => object} getRecord current record
 * @param {string} fieldName field holding the execution state
 * @param {(record: object) => Promise} reload what to reload once finished
 * @param {(record: object) => Promise} [onFinished] called after the reload
 */
function useRefreshWhileRunning(getRecord, fieldName, reload, onFinished) {
    const orm = useService("orm");
    let timer = null;
    let stopped = false;

    const stop = () => {
        stopped = true;
        clearTimeout(timer);
        timer = null;
    };
    const schedule = (check) => {
        clearTimeout(timer);
        timer = setTimeout(check, POLL_DELAY);
    };

    useEffect(
        (value, resId) => {
            stopped = false;
            if (value !== RUNNING || !resId) {
                return stop;
            }
            const record = getRecord();
            const check = async () => {
                if (stopped) {
                    return;
                }
                if (document.hidden || record.dirty) {
                    // Do not reload a hidden tab, nor discard the user's edits.
                    return schedule(check);
                }
                let current = RUNNING;
                try {
                    const [data] = await orm.read(record.resModel, [resId], [fieldName]);
                    current = data ? data[fieldName] : null;
                } catch {
                    // Temporary network error: try again later.
                }
                if (stopped) {
                    return;
                }
                if (current === RUNNING) {
                    return schedule(check);
                }
                await reload(record);
                if (onFinished) {
                    await onFinished(record);
                }
            };
            schedule(check);
            return stop;
        },
        () => [getRecord().data[fieldName], getRecord().resId]
    );
}

/**
 * Invisible form widget: reloads the plan form when its execution ends and
 * shows the result in a notification.
 */
export class PrimetechCloneAutoRefresh extends Component {
    static template = "primetech_database_test_clone.AutoRefresh";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        useRefreshWhileRunning(
            () => this.props.record,
            "execution_state",
            (record) => record.load(),
            (record) => this.notifyResult(record)
        );
    }

    async notifyResult(record) {
        const [log] = await this.orm.searchRead(
            "primetech.database.clone.log",
            [["plan_id", "=", record.resId]],
            ["state", "duration"],
            { limit: 1, order: "id desc" }
        );
        if (!log) {
            return;
        }
        if (log.state === "done") {
            this.notification.add(
                _t("Exécution terminée en %s s.", Math.round(log.duration || 0)),
                { type: "success" }
            );
        } else if (log.state === "failed") {
            this.notification.add(_t("L'exécution a échoué : consultez le Journal."), {
                type: "danger",
            });
        }
    }
}

registry.category("view_widgets").add("primetech_clone_autorefresh", {
    component: PrimetechCloneAutoRefresh,
});

/**
 * Badge that refreshes its list (or form) as soon as the "running" state of
 * its record changes. Used for the plan status and the journal state.
 */
export class PrimetechRunningBadge extends BadgeField {
    static template = "web.BadgeField";

    setup() {
        super.setup();
        useRefreshWhileRunning(
            () => this.props.record,
            this.props.name,
            (record) => record.model.load()
        );
    }
}

registry.category("fields").add("primetech_running_badge", {
    ...badgeField,
    component: PrimetechRunningBadge,
});
