from odoo import _, api, fields, models

from .stone_order import STATES as STONE_ORDER_STATES


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    stone_order_ids = fields.One2many(
        "jewelry.stone.order", "repair_order_id", string="Stone Orders"
    )
    stone_order_count = fields.Integer(compute="_compute_stone_order_info")
    last_stone_order_state = fields.Selection(
        STONE_ORDER_STATES,
        string="Last Stone Order",
        compute="_compute_stone_order_info",
    )
    stone_order_incomplete = fields.Boolean(compute="_compute_stone_order_info")

    @api.depends(
        "stone_order_ids.state",
        "stone_order_ids.shipped_complete",
    )
    def _compute_stone_order_info(self):
        for order in self:
            orders = order.stone_order_ids.sorted("id")
            order.stone_order_count = len(orders)
            order.last_stone_order_state = orders[-1].state if orders else False
            order.stone_order_incomplete = any(
                so.state in ("shipped", "received") and not so.shipped_complete
                for so in orders
            )

    def action_open_stone_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Stone Orders"),
            "res_model": "jewelry.stone.order",
            "view_mode": "tree,form",
            "domain": [("repair_order_id", "=", self.id)],
            "context": {
                "default_repair_order_id": self.id,
                "default_purpose": "repair",
            },
        }

    def action_order_stones(self):
        """Open a draft stone order prefilled from the Stones tab."""
        self.ensure_one()
        lines = [
            (0, 0, {
                "gem_type_id": gem.gem_type_id.id,
                "origin": gem.origin,
                "cut_shape": gem.cut_shape,
                "standard_size_id": gem.standard_size_id.id,
                "quantity": gem.quantity,
                "weight_ct": gem.weight_ct,
                "certificate_ref": gem.certificate_id.name if gem.quantity == 1 else False,
            })
            for gem in self.gem_line_ids
        ]
        return {
            "type": "ir.actions.act_window",
            "name": _("Order Stones"),
            "res_model": "jewelry.stone.order",
            "view_mode": "form",
            "context": {
                "default_repair_order_id": self.id,
                "default_purpose": "repair",
                "default_request_line_ids": lines,
            },
        }
