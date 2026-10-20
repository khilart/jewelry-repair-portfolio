from odoo import api, fields, models

PHOTO_KINDS = [
    ("intake", "At Intake"),
    ("progress", "In Progress"),
    ("finished", "Finished Work"),
]


class JewelryRepairPhoto(models.Model):
    _name = "jewelry.repair.photo"
    _description = "Jewelry Repair Order Photo"
    _order = "sequence, id"

    order_id = fields.Many2one(
        "jewelry.repair.order", string="Order", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    image = fields.Image(string="Photo", max_width=2160, max_height=3840, required=True)
    image_256 = fields.Image(
        string="Thumbnail",
        related="image",
        max_width=256,
        max_height=256,
        store=True,
        attachment=False,
    )
    kind = fields.Selection(PHOTO_KINDS, string="Kind", required=True, default="progress")
    caption = fields.Char(string="Caption")

    @api.depends("caption", "kind", "order_id.name")
    def _compute_display_name(self):
        """Odoo 17 builds display_name here; name_get no longer feeds it."""
        kinds = dict(self._fields["kind"].selection)
        for photo in self:
            photo.display_name = (
                photo.caption or kinds.get(photo.kind) or photo.order_id.name or ""
            )


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    photo_ids = fields.One2many("jewelry.repair.photo", "order_id", string="Photos")
    photo_count = fields.Integer(compute="_compute_photo_count")

    @api.depends("photo_ids")
    def _compute_photo_count(self):
        for order in self:
            order.photo_count = len(order.photo_ids)

    def _finished_work_photo(self):
        """The latest photo of the finished work, if anyone took one.

        `item_image` stays what it has always been — the shot taken at intake — and
        keeps feeding the portal, the order card, the kanban and the delivery lines.
        """
        self.ensure_one()
        finished = self.photo_ids.filtered(lambda photo: photo.kind == "finished")
        return finished[-1] if finished else self.env["jewelry.repair.photo"]
