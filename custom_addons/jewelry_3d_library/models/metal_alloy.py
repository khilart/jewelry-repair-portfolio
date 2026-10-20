from odoo import fields, models


class JewelryMetalAlloy(models.Model):
    _inherit = "jewelry.metal.alloy"

    density = fields.Float(
        string="Density (g/cm³)",
        digits=(16, 4),
        help="Alloy density for weight estimation from STL volume. "
             "Examples: Au999 ≈ 19.3, Au750 ≈ 15.5, Au585 ≈ 13.5, Ag925 ≈ 10.3.",
    )
