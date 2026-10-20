from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryOrderAreaLoss(models.Model):
    _name = "jewelry.order.area.loss"
    _description = "Order Metal Loss by Work Area"
    _order = "area_id"

    order_id = fields.Many2one(
        "jewelry.repair.order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    order_received_date = fields.Datetime(
        related="order_id.received_date",
        string="Order Date",
        store=True,
        readonly=True,
        index=True,
    )
    order_partner_id = fields.Many2one(
        "res.partner",
        related="order_id.partner_id",
        string="Client",
        store=True,
        readonly=True,
        index=True,
    )
    area_id = fields.Many2one(
        "jewelry.work.area",
        string="Work Area",
        required=True,
        ondelete="restrict",
    )
    weight_in = fields.Float(string="Weight In (g)", digits=(16, 3))
    weight_out = fields.Float(string="Weight Out (g)", digits=(16, 3))
    loss = fields.Float(
        string="Loss (g)",
        digits=(16, 3),
        compute="_compute_loss",
        store=True,
    )
    loss_percent = fields.Float(
        string="Loss %",
        digits=(16, 2),
        compute="_compute_loss",
        store=True,
        group_operator="avg",
    )

    @api.depends("weight_in", "weight_out")
    def _compute_loss(self):
        for rec in self:
            rec.loss = rec.weight_in - rec.weight_out
            rec.loss_percent = (rec.loss / rec.weight_in * 100.0) if rec.weight_in else 0.0

    def action_open_order(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'jewelry.repair.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class JewelryOrderClientLoss(models.Model):
    _name = "jewelry.order.client.loss"
    _description = "Order Metal Loss by Client"
    _auto = False
    _order = "partner_id"

    order_id = fields.Many2one("jewelry.repair.order", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Client", readonly=True)
    item_type_id = fields.Many2one("jewelry.repair.item.type", string="Item Type", readonly=True)
    new_product_manufacturing = fields.Boolean(string="New Product Manufacturing", readonly=True)
    received_date = fields.Datetime(string="Order Date", readonly=True)
    received_weight = fields.Float(string="Weight In (g)", digits=(16, 3), readonly=True)
    metal_delivered_weight = fields.Float(string="Weight Out (g)", digits=(16, 3), readonly=True)
    added_weight = fields.Float(string="Added (g)", digits=(16, 3), readonly=True)
    invoiced_weight = fields.Float(
        string="Invoiced (g)",
        digits=(16, 3),
        readonly=True,
        help="Metal billed to the client, from stock or not. Shown for reference only: "
             "it is sold metal, so it is not part of the loss balance.",
    )
    returned_weight = fields.Float(string="Return (g)", digits=(16, 3), readonly=True)
    loss = fields.Float(string="Loss (g)", digits=(16, 3), readonly=True)
    loss_percent = fields.Float(
        string="Loss %", digits=(16, 2), readonly=True, group_operator="avg"
    )
    loss_sign = fields.Selection(
        [
            ("loss", "Loss"),
            ("gain", "Negative Loss"),
            ("zero", "No Loss"),
            ("invalid", "Invalid Data"),
        ],
        string="Loss Sign",
        readonly=True,
    )

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS jewelry_order_client_loss")
        self.env.cr.execute("""
            CREATE VIEW jewelry_order_client_loss AS (
                SELECT
                    base.*,
                    CASE WHEN base.received_weight + base.added_weight > 0
                        THEN base.loss / (base.received_weight + base.added_weight) * 100.0
                        ELSE 0
                    END AS loss_percent,
                    CASE
                        -- No metal in, or no metal out: the weights were never entered,
                        -- so the balance is meaningless rather than a loss.
                        WHEN base.received_weight + base.added_weight <= 0 THEN 'invalid'
                        WHEN base.metal_delivered_weight + base.returned_weight <= 0 THEN 'invalid'
                        WHEN base.loss > 0.0005 THEN 'loss'
                        WHEN base.loss < -0.0005 THEN 'gain'
                        ELSE 'zero'
                    END AS loss_sign
                FROM (
                    SELECT
                        ro.id,
                        ro.id AS order_id,
                        ro.partner_id,
                        ro.item_type_id,
                        ro.new_product_manufacturing,
                        ro.received_date,
                        COALESCE(ro.received_weight, 0) AS received_weight,
                        COALESCE(ro.metal_delivered_weight, 0) AS metal_delivered_weight,
                        COALESCE(mat.added_weight, 0) AS added_weight,
                        COALESCE(mat.invoiced_weight, 0) AS invoiced_weight,
                        COALESCE(mat.returned_weight, 0) AS returned_weight,
                        COALESCE(ro.received_weight, 0)
                            + COALESCE(mat.added_weight, 0)
                            - COALESCE(ro.metal_delivered_weight, 0)
                            - COALESCE(mat.returned_weight, 0) AS loss
                    FROM jewelry_repair_order ro
                    LEFT JOIN (
                        SELECT
                            order_id,
                            SUM(CASE WHEN return_to_storage IS TRUE
                                THEN COALESCE(weight, 0) ELSE 0 END) AS returned_weight,
                            -- Workshop metal put into the piece: taken from stock and
                            -- not billed to the client. Invoiced material is sold, not lost.
                            SUM(CASE WHEN return_to_storage IS NOT TRUE
                                      AND consume_from_stock IS TRUE
                                      AND include_in_invoice IS NOT TRUE
                                THEN COALESCE(weight, 0) ELSE 0 END) AS added_weight,
                            -- Reference only: every gram billed to the client, whether or
                            -- not it was written off from stock. Sold metal, not a loss.
                            SUM(CASE WHEN return_to_storage IS NOT TRUE
                                      AND include_in_invoice IS TRUE
                                THEN COALESCE(weight, 0) ELSE 0 END) AS invoiced_weight
                        FROM jewelry_repair_material_line
                        GROUP BY order_id
                    ) mat ON mat.order_id = ro.id
                    WHERE ro.state = 'delivered'
                ) base
            )
        """)

    def action_open_order(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'jewelry.repair.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
