/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanHeader } from "@web/views/kanban/kanban_header";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { useState, useEffect } from "@odoo/owl";

const PLANNING_DATE_STORAGE_KEY = "jewelry_repair_work_operations_planning_date";
const PLANNING_PANEL_VISIBLE_KEY = "jewelry_repair_planning_panel_visible";
const SEARCH_PANEL_VISIBLE_KEY = "jewelry_repair_search_panel_visible";

function getStoredPlanningDate() {
    return window.localStorage.getItem(PLANNING_DATE_STORAGE_KEY) || new Date().toISOString().slice(0, 10);
}

function setStoredPlanningDate(value) {
    if (value) {
        window.localStorage.setItem(PLANNING_DATE_STORAGE_KEY, value);
    } else {
        window.localStorage.removeItem(PLANNING_DATE_STORAGE_KEY);
    }
}

function formatMinutes(totalMinutes) {
    const roundedMinutes = Math.round(totalMinutes || 0);
    const days = Math.floor(roundedMinutes / (8 * 60));
    const remainder = roundedMinutes % (8 * 60);
    const hours = Math.floor(remainder / 60);
    const minutes = remainder % 60;
    const parts = [];
    if (days) {
        parts.push(`${days} d`);
    }
    if (hours) {
        parts.push(`${hours} h`);
    }
    if (minutes || !parts.length) {
        parts.push(`${minutes} m`);
    }
    return parts.join(" ");
}

function isRepairWorkOperationsModel(resModel) {
    return resModel === "jewelry.repair.order.operation";
}

patch(KanbanHeader.prototype, {
    get isRepairWorkOperationsBoard() {
        const resModel =
            this.props?.list?.model?.root?.resModel ||
            this.props?.list?.model?.config?.resModel ||
            this.props?.list?.resModel;
        return isRepairWorkOperationsModel(resModel);
    },

    get isRepairPlanningBoard() {
        if (!this.isRepairWorkOperationsBoard) return false;
        const context =
            this.props?.list?.model?.root?.context ||
            this.props?.list?.model?.config?.context ||
            {};
        return !!context.planning_board;
    },

    get repairColumnWorkloadDisplay() {
        if (!this.isRepairWorkOperationsBoard || !this.group || this.group.isFolded) {
            return "";
        }
        const records = this.group.list?.records || [];
        const totalMinutes = records.reduce(
            (acc, record) => acc + (record.data?.estimated_duration_minutes || 0),
            0
        );
        return formatMinutes(totalMinutes);
    },
});

const originalKanbanControllerSetup = KanbanController.prototype.setup;
patch(KanbanController.prototype, {
    setup() {
        originalKanbanControllerSetup.call(this);
        this.repairPlanningState = useState({
            date: getStoredPlanningDate(),
            panelVisible: window.localStorage.getItem(PLANNING_PANEL_VISIBLE_KEY) !== "false",
            searchPanelVisible: window.localStorage.getItem(SEARCH_PANEL_VISIBLE_KEY) !== "false",
        });

        if (this.isRepairWorkOperationsBoard) {
            useEffect(
                () => {
                    const panels = document.querySelectorAll(".o_search_panel");
                    panels.forEach((panel) => {
                        panel.classList.toggle("jr_search_panel_hidden", !this.repairPlanningState.searchPanelVisible);
                    });
                },
                () => [this.repairPlanningState.searchPanelVisible]
            );
        }
    },

    get isRepairWorkOperationsBoard() {
        return isRepairWorkOperationsModel(this.props?.resModel);
    },

    get planningDateValue() {
        return this.repairPlanningState?.date || "";
    },

    onPlanningDateChange(ev) {
        const value = ev.target.value || "";
        this.repairPlanningState.date = value;
        setStoredPlanningDate(value);
    },

    clearPlanningDate() {
        this.repairPlanningState.date = "";
        setStoredPlanningDate("");
    },

    get planningPanelVisible() {
        return this.repairPlanningState?.panelVisible !== false;
    },

    togglePlanningPanel() {
        this.repairPlanningState.panelVisible = !this.repairPlanningState.panelVisible;
        window.localStorage.setItem(PLANNING_PANEL_VISIBLE_KEY, this.repairPlanningState.panelVisible);
    },

    get searchPanelVisible() {
        return this.repairPlanningState?.searchPanelVisible !== false;
    },

    toggleSearchPanel() {
        this.repairPlanningState.searchPanelVisible = !this.repairPlanningState.searchPanelVisible;
        window.localStorage.setItem(SEARCH_PANEL_VISIBLE_KEY, this.repairPlanningState.searchPanelVisible);
    },
});

function findRecordByDataId(list, dataRecordId) {
    const targetId = String(dataRecordId);
    const rootList = list?.model?.root || list;
    const groupedRecords = (rootList?.groups || []).flatMap((group) => group.list.records || []);
    const flatRecords = rootList?.records || [];
    return [...groupedRecords, ...flatRecords].find((record) => String(record.id) === targetId);
}

const originalKanbanRendererSetup = KanbanRenderer.prototype.setup;
const originalSortRecordDrop = KanbanRenderer.prototype.sortRecordDrop;
patch(KanbanRenderer.prototype, {
    setup() {
        originalKanbanRendererSetup.call(this);
        this.orm = useService("orm");
    },

    async sortRecordDrop(dataRecordId, dataGroupId, params) {
        const resModel = this.props?.list?.model?.root?.resModel;
        if (!isRepairWorkOperationsModel(resModel)) {
            return originalSortRecordDrop.call(this, dataRecordId, dataGroupId, params);
        }

        const context = this.props?.list?.model?.root?.context || {};
        if (!context.planning_board) {
            return originalSortRecordDrop.call(this, dataRecordId, dataGroupId, params);
        }

        const planningDate = getStoredPlanningDate();
        const record = findRecordByDataId(this.props?.list, dataRecordId);
        const resId = record?.resId;
        const hasPlannedDate = !!record?.data?.planned_date;

        await originalSortRecordDrop.call(this, dataRecordId, dataGroupId, params);

        if (!planningDate || !resId || hasPlannedDate) {
            return;
        }

        await this.orm.write("jewelry.repair.order.operation", [resId], {
            planned_date: planningDate,
        });
        await this.props.list.model.root.load();
    },
});
