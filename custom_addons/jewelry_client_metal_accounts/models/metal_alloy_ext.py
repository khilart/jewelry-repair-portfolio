from odoo import fields, models


class JewelryMetalAlloy(models.Model):
    _inherit = "jewelry.metal.alloy"

    show_in_client_balance = fields.Boolean(
        string="Show in Client Balance",
        default=False,
        help="Include this alloy in the informational balance display on client metal accounts.",
    )
