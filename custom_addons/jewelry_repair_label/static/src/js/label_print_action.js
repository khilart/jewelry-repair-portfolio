/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { isSerialSupported, sendToPrinter } from "./label_printer";

export class LabelPrintAction extends Component {
    static template = "jewelry_repair_label.PrintAction";
    static props = ["*"];

    setup() {
        const params = this.props.action.params || {};
        this.orderId = params.order_id;
        this.orderName = params.order_name || "";
        this.state = useState({ message: "", failed: false, busy: false });
        this.supported = isSerialSupported();
    }

    get imageUrl() {
        return `/jewelry/repair/label/${this.orderId}.png`;
    }

    get streamUrl() {
        return `/jewelry/repair/label/${this.orderId}.tspl`;
    }

    async onPrint() {
        this.state.busy = true;
        this.state.failed = false;
        this.state.message = _t("Sending to the printer…");
        try {
            const response = await fetch(this.streamUrl);
            if (!response.ok) {
                throw new Error(_t("The label could not be built."));
            }
            const bytes = new Uint8Array(await response.arrayBuffer());
            await sendToPrinter(bytes);
            this.state.message = _t("Sent. The label should come out now.");
        } catch (error) {
            this.state.failed = true;
            this.state.message = error.message || String(error);
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("jewelry_repair_label.print", LabelPrintAction);
