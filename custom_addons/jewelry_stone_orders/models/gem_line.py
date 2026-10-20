from odoo import fields, models


class JewelryRepairGemLine(models.Model):
    _inherit = "jewelry.repair.gem.line"

    stone_order_line_id = fields.Many2one(
        "jewelry.stone.order.shipped.line",
        string="From Stone Order",
        readonly=True,
        copy=False,
        ondelete="set null",
        help="Where this stone came from. Makes the transfer repeatable instead of "
             "duplicating, and shows the origin of every stone in the order.",
    )
