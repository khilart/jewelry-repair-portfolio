/** @odoo-module **/

import { onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

/**
 * Scanning a label in the order list opens that order.
 *
 * The barcode service tells a scanner from a person by how fast the keys
 * arrive, and it ignores anything typed into an input, so this does not
 * interfere with typing in the search box.
 */

/** Order number as printed on the label, e.g. RO2026-0342. */
const ORDER_CODE = /^[A-Za-z]{2}\d{4}-\d+$/;

export class OrderScanListController extends ListController {
    setup() {
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");

        const barcode = useService("barcode");
        const onScan = (event) => this.openScannedOrder(event.detail.barcode);
        barcode.bus.addEventListener("barcode_scanned", onScan);
        onWillUnmount(() => barcode.bus.removeEventListener("barcode_scanned", onScan));
    }

    async openScannedOrder(scanned) {
        const code = (scanned || "").trim();
        if (!ORDER_CODE.test(code)) {
            // Plenty of other things in a workshop carry a barcode. Stay quiet.
            return;
        }
        const ids = await this.orm.search(
            this.props.resModel, [["name", "=", code]], { limit: 1 }
        );
        if (!ids.length) {
            this.notification.add(_t("No order found for %s.", code), { type: "warning" });
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: ids[0],
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("views").add("jewelry_order_scan_list", {
    ...listView,
    Controller: OrderScanListController,
});
