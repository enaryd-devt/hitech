/** @odoo-module **/

export const GLOBAL_DATE_FILTER_EVENT = "primetech-global-date-filter-changed";
const GLOBAL_DATE_FILTER_KEY = "primetech_reporting_center.global_date_filter";
const ALLOWED_PERIODS = new Set(["today", "week", "month", "year", "custom"]);
const DEFAULT_GLOBAL_DATE_FILTER = Object.freeze({ period: "month", dateFrom: "", dateTo: "" });

function dateInputValue(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function normaliseGlobalDateFilter(value = {}) {
    const period = ALLOWED_PERIODS.has(value.period) ? value.period : DEFAULT_GLOBAL_DATE_FILTER.period;
    return {
        period,
        dateFrom: typeof value.dateFrom === "string" ? value.dateFrom : "",
        dateTo: typeof value.dateTo === "string" ? value.dateTo : "",
    };
}

export function getDefaultCustomDateRange() {
    const today = new Date();
    return {
        dateFrom: dateInputValue(new Date(today.getFullYear(), today.getMonth(), 1)),
        dateTo: dateInputValue(today),
    };
}

export function getGlobalDateFilter() {
    try {
        const filter = normaliseGlobalDateFilter(JSON.parse(localStorage.getItem(GLOBAL_DATE_FILTER_KEY) || "{}"));
        return filter.period === "custom" && (!filter.dateFrom || !filter.dateTo)
            ? { ...filter, ...getDefaultCustomDateRange() }
            : filter;
    } catch {
        return { ...DEFAULT_GLOBAL_DATE_FILTER };
    }
}

export function setGlobalDateFilter(value) {
    const next = normaliseGlobalDateFilter({ ...getGlobalDateFilter(), ...value });
    try {
        localStorage.setItem(GLOBAL_DATE_FILTER_KEY, JSON.stringify(next));
    } catch {
        // The dashboard remains usable when storage is unavailable.
    }
    window.dispatchEvent(new CustomEvent(GLOBAL_DATE_FILTER_EVENT, { detail: next }));
    return next;
}

export function subscribeToGlobalDateFilter(callback) {
    const onLocalChange = (event) => callback(event.detail);
    const onStorageChange = (event) => {
        if (event.key === GLOBAL_DATE_FILTER_KEY) {
            callback(getGlobalDateFilter());
        }
    };
    window.addEventListener(GLOBAL_DATE_FILTER_EVENT, onLocalChange);
    window.addEventListener("storage", onStorageChange);
    return () => {
        window.removeEventListener(GLOBAL_DATE_FILTER_EVENT, onLocalChange);
        window.removeEventListener("storage", onStorageChange);
    };
}

export function globalDateFilterPayload(filter) {
    return {
        period: filter.period,
        date_from: filter.period === "custom" ? filter.dateFrom : false,
        date_to: filter.period === "custom" ? filter.dateTo : false,
    };
}

export const dashboardState = {

    save(key, state) {

        sessionStorage.setItem(
            key,
            JSON.stringify(state)
        );

    },

    load(key) {

        const value =
            sessionStorage.getItem(key);

        return value
            ? JSON.parse(value)
            : null;

    },

};
