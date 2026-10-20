/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

patch(ListController.prototype, {
    get isMetalRateList() {
        return this.props.resModel === "jewelry.metal.rate";
    },

    async onClickFetchKitcoGold() {
        await this.orm.call("jewelry.metal.rate", "action_add_kitco_gold_rate", []);
        await this.model.root.load();
        this.render();
    },
});
