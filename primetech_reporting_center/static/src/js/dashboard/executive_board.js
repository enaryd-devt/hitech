/** @odoo-module **/

import { Component, useRef, useState, onMounted, onPatched, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class ExecutiveBoard extends Component {
    static props = { filters: { type: Object, optional: true }, refreshKey: { optional: true }, "*": true };
    setup() {
        this.actionService = useService("action");
        this.boardRef = useRef("board");
        this.stateStorageKey = "primetechExecutiveBoardState";
        this.scrollStorageKey = "primetechExecutiveBoardScroll";
        this.boardSnapshotStorageKey = "primetechExecutiveBoardSnapshot";
        this.cacheTtlMs = 60 * 1000;
        const savedState = this.loadSavedState();
        const defaultKpiFilters = { cash_period: "today", billing_period: "month", stock_scope: "all", store_period: "week", revenue_period: "week", cashflow_period: "month", top_watch_period: "month", customer_receivable_filter: "all", supplier_receivable_filter: "all" };
        const defaultRevenueChartOptions = { income: true, expense: true, grid: true };
        const defaultKpiLoading = Object.fromEntries(Object.keys(defaultKpiFilters).map((key) => [key, false]));
        this.boardCache = new Map();
        this.kpiCache = new Map();
        this.currentRequestId = 0;
        this.kpiLoadingRequestIds = {};
        this.cashflowLabels = {
            title: _t("Suivi de trésorerie"),
            subtitle: _t("Encaissements, décaissements, charges et comptes d'encaissement"),
            periodAria: _t("Période du suivi de trésorerie"),
            today: _t("Aujourd’hui"),
            week: _t("Cette semaine"),
            month: _t("Ce mois"),
            year: _t("Cette année"),
            period: _t("Période"),
            from: _t("Du"),
            to: _t("Au"),
            startDate: _t("Date de début"),
            endDate: _t("Date de fin"),
            reportActions: _t("Actions du rapport"),
            previewReport: _t("Aperçu"),
            printReport: _t("Imprimer"),
            receipts: _t("Encaissements"),
            disbursements: _t("Décaissements"),
            netCashflow: _t("Flux net"),
            coverage: _t("Couverture"),
            expenses: _t("Charges comptabilisées"),
            analyzedPeriod: _t("Période analysée"),
            expenseAnalysis: _t("Analyse des comptes de charges"),
            receiptAnalysis: _t("Analyse des comptes d'encaissement"),
            foundAccounts: _t("compte(s) trouvé(s)"),
            searchExpense: _t("Rechercher un compte de charge…"),
            searchExpenseAria: _t("Rechercher un compte de charge"),
            searchReceipt: _t("Rechercher un compte d'encaissement…"),
            searchReceiptAria: _t("Rechercher un compte d'encaissement"),
            entries: _t("écriture(s)"),
            noExpenseAccount: _t("Aucun compte de charge ne correspond à votre recherche."),
            noReceiptAccount: _t("Aucun compte d'encaissement ne correspond à votre recherche."),
            historyTitle: _t("Activités et journal d’audit"),
            historySubtitle: _t("Les 100 derniers événements enregistrés dans le système"),
            viewAll: _t("Voir tout"),
            dateTime: _t("Date / Heure"),
            source: _t("Source"),
            user: _t("Utilisateur"),
            event: _t("Événement"),
            detail: _t("Détail"),
            document: _t("Document"),
            noHistory: _t("Aucun événement à afficher."),
            performanceTitle: _t("Indicateurs de performance"),
            viewAnalysis: _t("Voir l’analyse"),
            topWatchTitle: _t("Top produits à surveiller"),
            topWatchSubtitle: _t("Forte rotation et stock au seuil minimum"),
            topWatchPeriodAria: _t("Période de surveillance des produits"),
            product: _t("Produit"),
            category: _t("Rayon"),
            rotation: _t("Rotation"),
            stockStatus: _t("État du stock"),
            stock: _t("Stock"),
            sold: _t("vendus"),
            noWatchProduct: _t("Aucun produit à forte rotation n’a atteint le seuil minimum."),
        };
        this.state = useState({ loading: true, period: savedState.period || "today", dateFrom: savedState.dateFrom || "", dateTo: savedState.dateTo || "", kpiCustomRanges: savedState.kpiCustomRanges || {}, kpiLoading: defaultKpiLoading, clockTick: Date.now(), categoryMenuOpen: false, categoryChartView: savedState.categoryChartView === "chart" ? "chart" : "overview", categoryChartType: ["pie", "bar", "line"].includes(savedState.categoryChartType) ? savedState.categoryChartType : "pie", cashflowMenuOpen: false, topWatchMenuOpen: false, customerReceivableMenuOpen: false, supplierReceivableMenuOpen: false, revenueChartView: savedState.revenueChartView === "chart" ? "chart" : "overview", revenueChartOptions: { ...defaultRevenueChartOptions, ...(savedState.revenueChartOptions || {}) }, revenueChartHidden: Boolean(savedState.revenueChartHidden), kpiFilters: { ...defaultKpiFilters, ...(savedState.kpiFilters || {}) }, partnerSearch: { customers: savedState.partnerSearch?.customers || "", suppliers: savedState.partnerSearch?.suppliers || "" }, partnerSearchLoading: { customers: false, suppliers: false }, kpis: [], stores: [], store_summary: { total: 0, orders: 0, average_ticket: 0, active_stores: 0, store_count: 0 }, revenue_chart: { subtitle: "Mois en cours", items: [] }, categories: { total: 0, items: [] }, cash: [], banks: [], stock: {}, partner_balance_kpis: { customers: { rows: [] }, suppliers: { rows: [] } }, current_user: { name: "Directeur Général", status: "En ligne" }, alerts: [], quick_actions: [], activities: [], top_watch: [], history_items: [], performance: [] });
        this.state.cashflowChargeSearch = savedState.cashflowChargeSearch || "";
        this.state.cashflowReceiptSearch = savedState.cashflowReceiptSearch || "";
        this.state.cashflow_analysis = { period_label: _t("Ce mois"), receipts: 0, disbursements: 0, net_cashflow: 0, coverage_rate: 0, total_expenses: 0, expense_accounts: [], all_expense_accounts: [], receipt_accounts: [], all_receipt_accounts: [] };
        for (const key of ["cash_period", "billing_period", "store_period", "revenue_period", "cashflow_period", "top_watch_period"]) {
            if (this.state.kpiFilters[key] === "custom") this.ensureKpiCustomRange(key);
        }
        onWillStart(() => {
            if (this.restoreBoardSnapshot()) {
                return;
            }
            return this.loadBoard({ force: true });
        });
        onMounted(() => {
            this.scrollContainer = this.getScrollContainer();
            this.restoreScroll();
            this.scrollListener = () => this.scheduleSaveScroll();
            this.scrollContainer.addEventListener("scroll", this.scrollListener, { passive: true });
            this.clockInterval = setInterval(() => {
                this.state.clockTick = Date.now();
            }, 1000);
            const refreshBoard = () => {
                if (document.visibilityState === "visible") {
                    this.loadBoard({ silent: true, force: true }).catch(() => {});
                }
            };
            const nextRefreshAt = this.nextBoardRefreshAt || Date.now() + this.cacheTtlMs;
            this.refreshTimeout = setTimeout(() => {
                refreshBoard();
                this.refreshInterval = setInterval(refreshBoard, this.cacheTtlMs);
            }, Math.max(0, nextRefreshAt - Date.now()));
            if ("ResizeObserver" in window) {
                this.kpiResizeObserver = new ResizeObserver(() => this.scheduleKpiValueFit());
                this.kpiResizeObserver.observe(this.boardRef.el.querySelector(".pt-eb-kpis"));
            } else {
                this.kpiResizeListener = () => this.scheduleKpiValueFit();
                window.addEventListener("resize", this.kpiResizeListener, { passive: true });
            }
            this.scheduleKpiValueFit();
        });
        onPatched(() => this.scheduleKpiValueFit());
        onWillUnmount(() => {
            if (this.clockInterval) {
                clearInterval(this.clockInterval);
            }
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            if (this.refreshTimeout) {
                clearTimeout(this.refreshTimeout);
            }
            if (this.scrollListener) {
                this.scrollContainer?.removeEventListener("scroll", this.scrollListener);
            }
            if (this.scrollSaveTimeout) {
                clearTimeout(this.scrollSaveTimeout);
            }
            Object.values(this.partnerSearchTimeouts || {}).forEach((timeout) => clearTimeout(timeout));
            this.kpiResizeObserver?.disconnect();
            if (this.kpiResizeListener) window.removeEventListener("resize", this.kpiResizeListener);
            if (this.kpiFitFrame) cancelAnimationFrame(this.kpiFitFrame);
            this.saveDashboardState();
            if (this.boardRef.el) {
                this.saveScroll();
            }
        });
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.refreshKey !== this.props.refreshKey) {
                await this.loadBoard();
            }
        });
    }

    getBoardFilters() {
        return {
            ...(this.props.filters || {}),
            period: this.state.period,
            date_from: this.state.period === "custom" ? this.state.dateFrom : null,
            date_to: this.state.period === "custom" ? this.state.dateTo : null,
            kpi_filters: { ...this.state.kpiFilters },
            kpi_custom_ranges: Object.fromEntries(Object.entries(this.state.kpiCustomRanges).map(([key, range]) => [key, { date_from: range.dateFrom, date_to: range.dateTo }])),
            partner_search: { ...this.state.partnerSearch },
        };
    }

    getBoardCacheKey(filters = this.getBoardFilters()) {
        return JSON.stringify(filters);
    }

    isCacheFresh(entry) {
        return Boolean(entry && Date.now() - entry.cachedAt < this.cacheTtlMs);
    }

    rememberBoardData(key, data, cachedAt = Date.now()) {
        const entry = { data, cachedAt };
        this.nextBoardRefreshAt = cachedAt + this.cacheTtlMs;
        this.boardCache.set(key, entry);
        if (this.boardCache.size > 12) {
            this.boardCache.delete(this.boardCache.keys().next().value);
        }
        try {
            sessionStorage.setItem(this.boardSnapshotStorageKey, JSON.stringify({ key, ...entry }));
        } catch {
            // The dashboard remains fully functional when browser storage is unavailable or full.
        }
    }

    restoreBoardSnapshot() {
        try {
            const snapshot = JSON.parse(sessionStorage.getItem(this.boardSnapshotStorageKey) || "null");
            const key = this.getBoardCacheKey();
            if (!snapshot?.data || snapshot.key !== key || !snapshot.cachedAt) {
                return false;
            }
            this.boardCache.set(key, snapshot);
            this.nextBoardRefreshAt = snapshot.cachedAt + this.cacheTtlMs;
            this.applyBoardData(snapshot.data);
            if (!this.isCacheFresh(snapshot)) {
                this.loadBoard({ silent: true, force: true }).catch(() => {});
            }
            return true;
        } catch {
            return false;
        }
    }

    getKpiCacheKey(key, filters = this.getBoardFilters()) {
        return JSON.stringify({
            key,
            filters: this.props.filters || {},
            globalPeriod: filters.period,
            globalDateFrom: filters.date_from,
            globalDateTo: filters.date_to,
            value: filters.kpi_filters?.[key],
            customRange: filters.kpi_custom_ranges?.[key] || {},
        });
    }

    rememberKpiData(key, data) {
        this.kpiCache.set(key, { data, cachedAt: Date.now() });
        if (this.kpiCache.size > 32) {
            this.kpiCache.delete(this.kpiCache.keys().next().value);
        }
    }

    applyKpiData(data) {
        Object.assign(this.state, data || {});
        if (data?.partner_balance_kpis) {
            for (const type of ["customers", "suppliers"]) {
                this.filterPartnerRows(type);
            }
        }
        if (data?.cashflow_analysis) {
            this.filterCashflowExpenseAccounts();
            this.filterCashflowReceiptAccounts();
        }
        if (this.latestBoardData && data) {
            Object.assign(this.latestBoardData, data);
            this.rememberBoardData(this.getBoardCacheKey(), this.latestBoardData);
        }
    }

    applyBoardData(data, options = {}) {
        this.latestBoardData = data;
        Object.assign(this.state, data, { loading: false });
        if (options.force) {
            this.kpiCache.clear();
        }
        for (const type of ["customers", "suppliers"]) {
            this.filterPartnerRows(type);
        }
        this.filterCashflowExpenseAccounts();
        this.filterCashflowReceiptAccounts();
        if (options.restoreScroll) {
            this.restoreScroll();
        }
    }

    async loadBoard(options = {}) {
        const filters = this.getBoardFilters();
        const cacheKey = this.getBoardCacheKey(filters);
        const cachedEntry = this.boardCache.get(cacheKey);
        if (this.isCacheFresh(cachedEntry) && !options.force) {
            this.applyBoardData(cachedEntry.data, options);
            return;
        }
        if (!options.silent && !this.state.kpis.length) {
            this.state.loading = true;
        }
        const requestId = ++this.currentRequestId;
        const data = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_executive_board",
            args: [filters],
            kwargs: {},
        });
        this.rememberBoardData(cacheKey, data);
        if (requestId === this.currentRequestId) {
            this.applyBoardData(data, options);
        }
    }

    async onPeriodChange(ev) {
        const nextPeriod = ev.target.value;
        if (nextPeriod === this.state.period) {
            return;
        }
        this.state.period = nextPeriod;
        if (nextPeriod === "custom" && (!this.state.dateFrom || !this.state.dateTo)) {
            const today = new Date();
            const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
            this.state.dateFrom ||= this.toDateInputValue(monthStart);
            this.state.dateTo ||= this.toDateInputValue(today);
        }
        this.saveDashboardState();
        await this.loadBoard({ silent: true });
    }

    async onCustomDateChange(key, ev) {
        this.state[key] = ev.target.value;
        this.saveDashboardState();
        if (this.state.dateFrom && this.state.dateTo && this.state.dateFrom <= this.state.dateTo) {
            await this.loadBoard({ silent: true });
        }
    }

    toDateInputValue(value) {
        const localDate = new Date(value.getTime() - value.getTimezoneOffset() * 60000);
        return localDate.toISOString().slice(0, 10);
    }

    async onKpiFilterChange(key, ev) {
        const nextValue = ev.target.value;
        if (nextValue === this.state.kpiFilters[key]) {
            return;
        }
        this.state.kpiFilters[key] = nextValue;
        if (nextValue === "custom") {
            this.ensureKpiCustomRange(key);
        }
        this.saveDashboardState();
        await this.loadKpiBoard(key);
    }

    ensureKpiCustomRange(key) {
        const current = this.state.kpiCustomRanges[key] || {};
        if (!current.dateFrom || !current.dateTo) {
            const today = new Date();
            this.state.kpiCustomRanges[key] = {
                dateFrom: current.dateFrom || this.toDateInputValue(new Date(today.getFullYear(), today.getMonth(), 1)),
                dateTo: current.dateTo || this.toDateInputValue(today),
            };
        }
        return this.state.kpiCustomRanges[key];
    }

    kpiCustomRange(key) {
        return this.state.kpiCustomRanges[key] || { dateFrom: "", dateTo: "" };
    }

    async onKpiCustomDateChange(key, field, ev) {
        const range = { ...this.kpiCustomRange(key), [field]: ev.target.value };
        this.state.kpiCustomRanges[key] = range;
        this.saveDashboardState();
        if (range.dateFrom && range.dateTo && range.dateFrom <= range.dateTo) {
            await this.loadKpiBoard(key);
        }
    }

    isKpiLoading(key) {
        return Boolean(this.state.kpiLoading[key]);
    }

    async loadKpiBoard(key, options = {}) {
        const requestId = (this.kpiLoadingRequestIds[key] || 0) + 1;
        this.kpiLoadingRequestIds[key] = requestId;
        this.state.kpiLoading[key] = true;
        try {
            const filters = this.getBoardFilters();
            const cacheKey = this.getKpiCacheKey(key, filters);
            const cachedEntry = this.kpiCache.get(cacheKey);
            if (cachedEntry) {
                this.applyKpiData(cachedEntry.data);
                if (this.isCacheFresh(cachedEntry) && !options.force) {
                    return;
                }
            }
            const data = await rpc("/web/dataset/call_kw", {
                model: "primetech.dashboard",
                method: "get_executive_kpi",
                args: [key, filters],
                kwargs: {},
            });
            this.rememberKpiData(cacheKey, data);
            if (this.kpiLoadingRequestIds[key] === requestId) {
                this.applyKpiData(data);
            }
        } finally {
            if (this.kpiLoadingRequestIds[key] === requestId) {
                this.state.kpiLoading[key] = false;
            }
        }
    }

    onPartnerSearchInput(type, ev) {
        // Read the DOM value explicitly; this avoids depending on directive
        // execution order between t-model and the input event handler.
        this.state.partnerSearch[type] = ev.target.value;
        this.partnerSearchTimeouts ||= {};
        clearTimeout(this.partnerSearchTimeouts[type]);
        this.partnerSearchTimeouts[type] = setTimeout(() => {
            this.filterPartnerRows(type);
        }, 120);
    }

    resetPartnerSearch(type) {
        this.state.partnerSearch[type] = "";
        this.filterPartnerRows(type);
    }

    filterPartnerRows(type) {
        const kpi = this.state.partner_balance_kpis[type];
        if (!kpi) return;
        const normalize = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
        const term = normalize(this.state.partnerSearch[type].trim());
        const allRows = kpi.all_rows || [];
        if (!term) {
            kpi.rows = [...(kpi.default_rows || allRows)];
            kpi.filtered_count = kpi.default_filtered_count ?? allRows.length;
            return;
        }
        const matches = allRows.filter((row) => normalize(row.partner).includes(term));
        kpi.rows = matches;
        kpi.filtered_count = matches.length;
    }

    onCashflowChargeSearch(ev) {
        this.state.cashflowChargeSearch = ev.target.value;
        this.filterCashflowExpenseAccounts();
        this.saveDashboardState();
    }

    onCashflowReceiptSearch(ev) {
        this.state.cashflowReceiptSearch = ev.target.value;
        this.filterCashflowReceiptAccounts();
        this.saveDashboardState();
    }

    toggleCashflowMenu() {
        this.state.cashflowMenuOpen = !this.state.cashflowMenuOpen;
    }

    toggleTopWatchMenu() {
        this.state.topWatchMenuOpen = !this.state.topWatchMenuOpen;
    }

    topWatchReportRows() {
        return (this.state.top_watch || []).map((row) => ({
            product: row.product,
            rayon: row.rayon,
            status: row.status,
            status_tone: row.status_tone,
            stock: row.stock,
            rotation: row.rotation,
        }));
    }

    async previewCashflowReport() {
        this.state.cashflowMenuOpen = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_cashflow_preview_action",
            args: [this.getBoardFilters()],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    async printCashflowReport() {
        this.state.cashflowMenuOpen = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_cashflow_print_action",
            args: [this.getBoardFilters()],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    async previewTopWatchReport() {
        this.state.topWatchMenuOpen = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_top_watch_preview_action",
            args: [this.getBoardFilters(), this.topWatchReportRows()],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    async printTopWatchReport() {
        this.state.topWatchMenuOpen = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_top_watch_print_action",
            args: [this.getBoardFilters(), this.topWatchReportRows()],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    partnerBalanceMenuStateKey(type) {
        return type === "suppliers" ? "supplierReceivableMenuOpen" : "customerReceivableMenuOpen";
    }

    togglePartnerBalanceMenu(type) {
        const key = this.partnerBalanceMenuStateKey(type);
        this.state[key] = !this.state[key];
    }

    partnerBalanceReportRows(type) {
        return (this.state.partner_balance_kpis[type]?.rows || []).map((row) => ({
            partner: row.partner,
            debit: row.debit,
            credit: row.credit,
            balance: row.balance,
            status: row.status,
            status_class: row.status_class,
        }));
    }

    partnerBalanceReportSummary(type) {
        const kpi = this.state.partner_balance_kpis[type] || {};
        return {
            total: kpi.total,
            filtered_count: kpi.filtered_count,
            filter: kpi.filter,
            search_term: this.state.partnerSearch[type] || "",
        };
    }

    async previewPartnerBalanceReport(type) {
        this.state[this.partnerBalanceMenuStateKey(type)] = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_partner_balance_preview_action",
            args: [type, this.partnerBalanceReportRows(type), this.partnerBalanceReportSummary(type)],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    async printPartnerBalanceReport(type) {
        this.state[this.partnerBalanceMenuStateKey(type)] = false;
        const action = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_partner_balance_print_action",
            args: [type, this.partnerBalanceReportRows(type), this.partnerBalanceReportSummary(type)],
            kwargs: {},
        });
        return this.actionService.doAction(action);
    }

    filterCashflowExpenseAccounts() {
        const analysis = this.state.cashflow_analysis;
        if (!analysis) return;
        const normalize = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
        const term = normalize(this.state.cashflowChargeSearch || "").trim();
        const accounts = analysis.all_expense_accounts || [];
        const matches = term
            ? accounts.filter((account) => normalize(`${account.code || ""} ${account.name || ""}`).includes(term))
            : accounts;
        analysis.expense_accounts = matches.slice(0, 12);
        analysis.filtered_expense_count = matches.length;
    }

    filterCashflowReceiptAccounts() {
        const analysis = this.state.cashflow_analysis;
        if (!analysis) return;
        const normalize = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
        const term = normalize(this.state.cashflowReceiptSearch || "").trim();
        const accounts = analysis.all_receipt_accounts || [];
        const matches = term
            ? accounts.filter((account) => normalize(`${account.code || ""} ${account.name || ""}`).includes(term))
            : accounts;
        analysis.receipt_accounts = matches.slice(0, 12);
        analysis.filtered_receipt_count = matches.length;
    }

    loadSavedState() {
        try {
            return JSON.parse(sessionStorage.getItem(this.stateStorageKey) || "{}");
        } catch {
            return {};
        }
    }

    saveDashboardState() {
        sessionStorage.setItem(this.stateStorageKey, JSON.stringify({
            period: this.state.period,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            kpiCustomRanges: this.state.kpiCustomRanges,
            kpiFilters: this.state.kpiFilters,
            categoryChartView: this.state.categoryChartView,
            categoryChartType: this.state.categoryChartType,
            revenueChartView: this.state.revenueChartView,
            revenueChartOptions: { ...this.state.revenueChartOptions },
            revenueChartHidden: this.state.revenueChartHidden,
            partnerSearch: { ...this.state.partnerSearch },
            cashflowChargeSearch: this.state.cashflowChargeSearch,
            cashflowReceiptSearch: this.state.cashflowReceiptSearch,
        }));
    }

    cashflowLabel(key) {
        return this.cashflowLabels[key] || "";
    }

    scheduleSaveScroll() {
        if (this.scrollSaveTimeout) {
            return;
        }
        this.scrollSaveTimeout = setTimeout(() => {
            this.saveScroll();
            this.scrollSaveTimeout = null;
        }, 150);
    }

    saveScroll() {
        const container = this.scrollContainer || this.getScrollContainer();
        const top = container === window
            ? window.scrollY || document.documentElement.scrollTop || 0
            : container.scrollTop;
        const containerTop = container === window ? 0 : container.getBoundingClientRect().top;
        const anchors = [...(this.boardRef.el?.querySelectorAll("[data-scroll-key]") || [])];
        const anchor = anchors.filter((item) => item.getBoundingClientRect().top <= containerTop + 2).at(-1);
        const anchorTop = anchor ? anchor.getBoundingClientRect().top - containerTop + top : 0;
        const scrollHeight = container === window ? document.documentElement.scrollHeight : container.scrollHeight;
        sessionStorage.setItem(this.scrollStorageKey, JSON.stringify({
            top,
            ratio: scrollHeight > 0 ? top / scrollHeight : 0,
            anchor: anchor?.dataset.scrollKey || null,
            anchorOffset: anchor ? top - anchorTop : 0,
            savedAt: Date.now(),
        }));
    }

    restoreScroll() {
        const storedValue = sessionStorage.getItem(this.scrollStorageKey);
        if (!storedValue) return;
        let savedScroll = 0;
        let savedState = {};
        try {
            const parsed = JSON.parse(storedValue);
            savedState = typeof parsed === "object" && parsed ? parsed : {};
            savedScroll = Number(parsed?.top ?? parsed) || 0;
        } catch {
            savedScroll = Number(storedValue) || 0;
        }
        const container = this.scrollContainer || this.getScrollContainer();
        const applyScroll = () => {
            let target = savedScroll;
            const anchor = savedState.anchor
                ? this.boardRef.el?.querySelector(`[data-scroll-key="${savedState.anchor}"]`)
                : null;
            if (anchor) {
                const currentTop = container === window ? window.scrollY : container.scrollTop;
                const containerTop = container === window ? 0 : container.getBoundingClientRect().top;
                const anchorTop = anchor.getBoundingClientRect().top - containerTop + currentTop;
                target = anchorTop + (Number(savedState.anchorOffset) || 0);
            } else if (savedState.ratio) {
                const height = container === window ? document.documentElement.scrollHeight : container.scrollHeight;
                target = height * savedState.ratio;
            }
            if (container === window) {
                if (Math.abs(window.scrollY - target) > 1) window.scrollTo(0, target);
            } else {
                if (Math.abs(container.scrollTop - target) > 1) container.scrollTop = target;
            }
        };
        requestAnimationFrame(() => {
            applyScroll();
            setTimeout(applyScroll, 80);
            setTimeout(applyScroll, 220);
        });
    }

    getScrollContainer() {
        let element = this.boardRef.el?.parentElement;
        while (element) {
            const style = window.getComputedStyle(element);
            if (/(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight) {
                return element;
            }
            element = element.parentElement;
        }
        return window;
    }

    revenueCurvePoints() {
        const items = this.state.revenue_chart.items || [];
        if (!items.length) return "0,55 100,55";
        const maximum = Math.max(...items.map((item) => Number(item.value) || 0));
        if (!maximum) return "0,55 100,55";
        const last = Math.max(items.length - 1, 1);
        return items.map((item, index) => {
            const ratio = Math.max(0, Math.min((Number(item.value) || 0) / maximum, 1));
            return `${(index / last) * 100},${88 - ratio * 76}`;
        }).join(" ");
    }

    revenueSummary() {
        const values = this.revenueCashflowSeries().map((item) => item.income + item.expense);
        const total = values.reduce((sum, value) => sum + value, 0);
        const nonZero = values.filter((value) => value > 0);
        const first = values[0] || 0;
        const last = values[values.length - 1] || 0;
        return { total, max: Math.max(...values, 0), min: nonZero.length ? Math.min(...nonZero) : 0, average: values.length ? total / values.length : 0, trend: first ? ((last - first) / first) * 100 : 0 };
    }

    revenueCashflowTotals() {
        return this.revenueCashflowSeries().reduce((totals, item) => ({
            income: totals.income + item.income,
            expense: totals.expense + item.expense,
        }), { income: 0, expense: 0 });
    }

    revenueCashflowAnalysis() {
        const summary = this.revenueSummary();
        const totals = this.revenueCashflowTotals();
        const net = totals.income + totals.expense;
        return {
            peak: summary.max,
            average: summary.average,
            minimum: summary.min,
            coverage: net ? (totals.expense / net) * 100 : 0,
            net,
        };
    }

    revenueCurveDots() {
        const items = this.state.revenue_chart.items || [];
        const maximum = Math.max(...items.map((item) => Number(item.value) || 0));
        const last = Math.max(items.length - 1, 1);
        return items.map((item, index) => ({ key: item.key, x: (index / last) * 100, y: maximum ? 88 - ((Number(item.value) || 0) / maximum) * 76 : 55 }));
    }


    revenueCashflowSeries() {
        const items = this.state.revenue_chart.items || [];
        return items.map((item, index) => {
            const income = Number(item.income ?? item.incoming ?? item.encaissements ?? item.value) || 0;
            const expense = Number(item.expense ?? item.outgoing ?? item.decaissements) || 0;
            return {
                key: item.key || `${item.label || "point"}-${index}`,
                label: item.label,
                income,
                expense,
            };
        });
    }

    revenueChartMaximum() {
        const series = this.revenueCashflowSeries();
        const options = this.state.revenueChartOptions || {};
        const maximum = Math.max(...series.flatMap((item) => [
            options.income ? item.income : 0,
            options.expense ? item.expense : 0,
        ]), 0);
        if (!maximum) {
            return 1;
        }
        const magnitude = 10 ** Math.max(Math.floor(Math.log10(maximum)) - 1, 0);
        return Math.ceil(maximum / magnitude) * magnitude;
    }

    revenueSeriesPoints(type) {
        const series = this.revenueCashflowSeries();
        const maximum = this.revenueChartMaximum();
        const last = Math.max(series.length - 1, 1);
        return series.map((item, index) => {
            const value = Math.max(0, Number(item[type]) || 0);
            return {
                key: `${type}-${item.key}`,
                label: item.label || `Période ${index + 1}`,
                value,
                x: series.length === 1 ? 50 : 8 + (index / last) * 84,
                y: 88 - Math.min(value / maximum, 1) * 80,
            };
        });
    }

    revenueIncomeBars() {
        const points = this.revenueSeriesPoints("income");
        const barWidth = Math.min(12, 70 / Math.max(points.length, 1));
        return points.map((point) => ({
            ...point,
            x: point.x - barWidth / 2,
            width: barWidth,
            height: 88 - point.y,
        }));
    }

    revenueSeriesPath(type) {
        const points = this.revenueSeriesPoints(type);
        if (!points.length) {
            return "M 0 88 L 100 88";
        }
        if (points.length === 1) {
            return `M ${points[0].x} ${points[0].y}`;
        }
        return points.reduce((path, point, index) => {
            if (!index) {
                return `M ${point.x} ${point.y}`;
            }
            const previous = points[index - 1];
            const controlOffset = (point.x - previous.x) * 0.45;
            return `${path} C ${previous.x + controlOffset} ${previous.y}, ${point.x - controlOffset} ${point.y}, ${point.x} ${point.y}`;
        }, "");
    }

    revenueSeriesDots(type) {
        return this.revenueSeriesPoints(type);
    }

    revenueGridLines() {
        return [0, 1, 2, 3, 4].map((index) => ({
            key: `grid-${index}`,
            y: 8 + index * 20,
        }));
    }

    revenueGridVerticalLines() {
        const points = this.revenueSeriesPoints("income");
        if (!points.length) {
            return [8, 29, 50, 71, 92].map((x, index) => ({ key: `grid-v-${index}`, x }));
        }
        return points.map((point) => ({ key: `grid-v-${point.key}`, x: point.x }));
    }
    revenueScaleLabels() {
        const maximum = this.revenueChartMaximum();
        return [maximum, maximum * .75, maximum * .5, maximum * .25, 0].map((value, index) => ({ key: `scale-${index}`, label: this.formatCompactAmount(value) }));
    }

    formatCompactAmount(value) {
        return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.round(value || 0));
    }

    formatKpiValue(value, suffix = "") {
        const numericValue = Number(value) || 0;
        const absoluteValue = Math.abs(numericValue);
        const scales = [
            { threshold: 1e12, divisor: 1e12, label: "T" },
            { threshold: 1e9, divisor: 1e9, label: "Md" },
            { threshold: 1e6, divisor: 1e6, label: "M" },
            { threshold: 1e3, divisor: 1e3, label: "K" },
        ];
        const scale = scales.find((item) => absoluteValue >= item.threshold);
        if (!scale) {
            return this.format(numericValue, suffix);
        }
        const scaledValue = numericValue / scale.divisor;
        const scaledAbsoluteValue = Math.abs(scaledValue);
        const maximumFractionDigits = scaledAbsoluteValue < 10 ? 2 : scaledAbsoluteValue < 100 ? 1 : 0;
        const compactValue = new Intl.NumberFormat("fr-FR", {
            minimumFractionDigits: 0,
            maximumFractionDigits,
        }).format(scaledValue);
        return `${compactValue} ${scale.label}${suffix ? ` ${suffix}` : ""}`;
    }

    scheduleKpiValueFit() {
        if (this.kpiFitFrame) cancelAnimationFrame(this.kpiFitFrame);
        this.kpiFitFrame = requestAnimationFrame(() => {
            this.kpiFitFrame = null;
            for (const element of this.boardRef.el?.querySelectorAll(".pt-eb-kpi-value") || []) {
                element.textContent = element.dataset.fullValue || "";
                element.classList.remove("is-compact");
                if (element.scrollWidth > element.clientWidth + 1) {
                    element.textContent = element.dataset.compactValue || element.dataset.fullValue || "";
                    element.classList.add("is-compact");
                }
            }
        });
    }

    categoryColor(index) {
        return ["#2f80ed", "#16a34a", "#fb923c", "#8b5cf6", "#64748b", "#ef4444"][index % 6];
    }

    categoryDonutStyle() {
        const items = this.categoryChartItems();
        if (!items.length) return "background: conic-gradient(#e2e8f0 0 100%)";
        let cursor = 0;
        const segments = items.map((item, index) => {
            const end = Math.min(cursor + (Number(item.percent) || 0), 100);
            const segment = `${this.categoryColor(index)} ${cursor}% ${end}%`;
            cursor = end;
            return segment;
        });
        if (cursor < 100) {
            segments.push(`#e2e8f0 ${cursor}% 100%`);
        }
        return `background: conic-gradient(${segments.join(", ")})`;
    }

    categoryChartItems() {
        const categories = this.state.categories || {};
        const rawItems = categories.items || [];
        const listedTotal = rawItems.reduce((sum, item) => sum + (Number(item.value) || 0), 0);
        const total = Math.max(Number(categories.total) || 0, listedTotal);
        const items = rawItems.map((item, index) => {
            const value = Math.max(0, Number(item.value) || 0);
            return {
                ...item,
                index,
                key: item.name || `category-${index}`,
                value,
                percent: total ? value / total * 100 : Number(item.percent) || 0,
            };
        });
        const otherValue = Math.max(total - listedTotal, 0);
        if (otherValue > .005) {
            items.push({
                index: items.length,
                key: "other-categories",
                name: _t("Autres catégories"),
                value: otherValue,
                percent: total ? otherValue / total * 100 : 0,
                action: null,
            });
        }
        return items;
    }

    categoryChartMaximum() {
        const maximum = Math.max(...this.categoryChartItems().map((item) => item.value), 0);
        if (!maximum) return 1;
        const magnitude = 10 ** Math.max(Math.floor(Math.log10(maximum)) - 1, 0);
        return Math.ceil(maximum / magnitude) * magnitude;
    }

    categoryChartPoints() {
        const items = this.categoryChartItems();
        const maximum = this.categoryChartMaximum();
        const last = Math.max(items.length - 1, 1);
        return items.map((item, index) => ({
            ...item,
            index,
            x: items.length === 1 ? 50 : 8 + (index / last) * 84,
            y: 88 - Math.min(item.value / maximum, 1) * 80,
        }));
    }

    categoryChartBars() {
        const points = this.categoryChartPoints();
        const width = Math.min(13, 68 / Math.max(points.length, 1));
        return points.map((point, index) => ({
            ...point,
            index,
            x: point.x - width / 2,
            width,
            height: 88 - point.y,
        }));
    }

    categoryChartLinePath() {
        const points = this.categoryChartPoints();
        if (!points.length) return "M 0 88 L 100 88";
        if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
        return points.reduce((path, point, index) => {
            if (!index) return `M ${point.x} ${point.y}`;
            const previous = points[index - 1];
            const controlOffset = (point.x - previous.x) * .45;
            return `${path} C ${previous.x + controlOffset} ${previous.y}, ${point.x - controlOffset} ${point.y}, ${point.x} ${point.y}`;
        }, "");
    }

    categoryChartGridLines() {
        return [0, 1, 2, 3, 4].map((index) => ({ key: `category-grid-${index}`, y: 8 + index * 20 }));
    }

    categoryChartGridVerticalLines() {
        const points = this.categoryChartPoints();
        return points.length
            ? points.map((point) => ({ key: `category-grid-v-${point.key}`, x: point.x }))
            : [8, 29, 50, 71, 92].map((x, index) => ({ key: `category-grid-v-${index}`, x }));
    }

    categoryScaleLabels() {
        const maximum = this.categoryChartMaximum();
        return [maximum, maximum * .75, maximum * .5, maximum * .25, 0]
            .map((value, index) => ({ key: `category-scale-${index}`, label: this.formatCompactAmount(value) }));
    }

    openCategoryChartWorkspace() {
        this.state.categoryMenuOpen = false;
        this.state.categoryChartView = "chart";
        this.saveDashboardState();
    }

    closeCategoryChartWorkspace() {
        this.state.categoryChartView = "overview";
        this.saveDashboardState();
    }

    setCategoryChartType(type) {
        if (!["pie", "bar", "line"].includes(type)) return;
        this.state.categoryChartType = type;
        this.saveDashboardState();
    }

    toggleRevenueChart() {
        this.state.revenueChartView = this.state.revenueChartView === "chart" ? "overview" : "chart";
        this.saveDashboardState();
    }

    openRevenueChartWorkspace() {
        this.state.revenueChartView = "chart";
        this.saveDashboardState();
    }

    closeRevenueChartWorkspace() {
        this.state.revenueChartView = "overview";
        this.saveDashboardState();
    }

    toggleRevenueChartOption(option, ev) {
        this.state.revenueChartOptions[option] = ev.target.checked;
        this.saveDashboardState();
    }

    openAction(action) {
        if (action) {
            this.saveDashboardState();
            this.saveScroll();
            this.auditDashboardAction(action);
            this.actionService.doAction(action);
        }
    }

    auditDashboardAction(action) {
        const actionLabel = String(action?.name || "").trim();
        if (!actionLabel) {
            return;
        }
        rpc("/primetech/audit/dashboard-action", {
            action_label: actionLabel,
            model_name: action.res_model || "primetech.dashboard",
            model_label: _t("Tableau de bord exécutif"),
            document_name: actionLabel,
            details: _t("Consultation depuis le tableau de bord exécutif."),
        }).catch(() => {});
    }

    toggleCategoryMenu(ev) {
        ev.stopPropagation();
        this.state.categoryMenuOpen = !this.state.categoryMenuOpen;
    }

    openCategoryAction(action) {
        this.state.categoryMenuOpen = false;
        this.openAction(action);
    }

    async refreshCategoryKpi() {
        this.state.categoryMenuOpen = false;
        await this.loadKpiBoard("revenue_period", { force: true });
    }

    userInitials() {
        const name = this.state.current_user?.name || "DG";
        return name.split(" ").filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    }

    todayLabel() {
        return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date());
    }

    timeLabel() {
        return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(this.state.clockTick));
    }

    format(value, suffix = "") {
        const amount = new Intl.NumberFormat("fr-FR").format(Math.round(value || 0));
        return suffix ? `${amount} ${suffix}` : amount;
    }

    formatPercent(value) {
        return `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0)} %`;
    }
}

ExecutiveBoard.template = "primetech_reporting_center.ExecutiveBoard";
