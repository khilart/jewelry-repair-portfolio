from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_stone_supplier = fields.Boolean(string="Stone Supplier")
    stone_commission_pct = fields.Float(
        string="Stone Commission %",
        digits=(16, 2),
        help="Our share of the price this supplier quotes to the client. Copied into a "
             "new stone order and frozen there.",
    )
