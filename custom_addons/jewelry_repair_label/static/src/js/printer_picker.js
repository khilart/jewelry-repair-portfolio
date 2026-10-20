/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { forgetPort, grantedPort, isSerialSupported, pickPort } from "./label_printer";

/**
 * Printer selection for the settings page.
 *
 * The choice belongs to the browser, not to the database: Web Serial grants
 * access per workstation, so this widget only shows whether the operator has
 * already picked a port here and lets them change it.
 */
export class PrinterPicker extends Component {
    static template = "jewelry_repair_label.PrinterPicker";
    static props = ["*"];

    setup() {
        this.state = useState({ selected: false, message: "" });
        this.supported = isSerialSupported();
        onWillStart(async () => {
            this.state.selected = Boolean(await grantedPort());
        });
    }

    async onPick() {
        try {
            await pickPort();
            this.state.selected = true;
            this.state.message = "";
        } catch (error) {
            // The picker throws when the operator closes it without choosing.
            this.state.message = error.name === "NotFoundError"
                ? _t("No printer was selected.")
                : error.message;
        }
    }

    async onForget() {
        await forgetPort();
        this.state.selected = Boolean(await grantedPort());
    }
}

export const printerPicker = { component: PrinterPicker };

registry.category("view_widgets").add("jewelry_label_printer_picker", printerPicker);
