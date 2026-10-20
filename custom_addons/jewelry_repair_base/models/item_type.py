from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairItemType(models.Model):
    _name = "jewelry.repair.item.type"
    _description = "Jewelry Repair Item Type"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    size_ids = fields.One2many("jewelry.repair.item.size", "item_type_id", string="Sizes")

    @api.model
    def name_create(self, name):
        if self.search([("name", "=ilike", name.strip())], limit=1):
            raise UserError(
                _("An item type named \"%s\" already exists. To create a duplicate, use \"Create and edit...\"") % name
            )
        return super().name_create(name)

    def action_load_standard_ring_sizes(self):
        self.ensure_one()
        # Standard ring sizes: EU size (circumference mm) / RU size (diameter mm)
        standard_sizes = [
            (44, 14.0), (45, 14.3), (46, 14.6), (47, 15.0), (48, 15.3),
            (49, 15.6), (50, 15.9), (51, 16.2), (52, 16.5), (53, 16.8),
            (54, 17.2), (55, 17.5), (56, 17.8), (57, 18.1), (58, 18.5),
            (59, 18.8), (60, 19.1), (61, 19.4), (62, 19.7), (63, 20.1),
            (64, 20.4), (65, 20.7), (66, 21.0), (67, 21.3), (68, 21.6),
            (69, 22.0), (70, 22.3),
        ]
        existing = set(self.size_ids.mapped("size_eu"))
        for eu, ru in standard_sizes:
            if eu not in existing:
                self.env["jewelry.repair.item.size"].create({
                    "item_type_id": self.id,
                    "size_eu": eu,
                    "size_ru": ru,
                    "sequence": eu,
                })


class JewelryRepairItemSize(models.Model):
    _name = "jewelry.repair.item.size"
    _description = "Jewelry Repair Item Size"
    _order = "sequence, size_eu"

    item_type_id = fields.Many2one(
        "jewelry.repair.item.type",
        string="Item Type",
        required=True,
        ondelete="cascade",
    )
    size_eu = fields.Float(string="EU Size", required=True)
    size_ru = fields.Float(string="RU Size")
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Size",
        compute="_compute_name",
        store=True,
    )

    @api.depends("size_eu", "size_ru")
    def _compute_name(self):
        for rec in self:
            eu = f"{rec.size_eu:.1f}"
            if rec.size_ru:
                ru = f"{rec.size_ru:g}"
                rec.name = f"{eu} / {ru}"
            else:
                rec.name = eu
