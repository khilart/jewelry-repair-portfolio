from odoo import api, models


class JewelryRepairOrderLineMixin(models.AbstractModel):
    """Editing guard shared by the content lines of a repair order.

    The order lock lives on the order, not on ``order.write``, so writing directly
    to a line cannot bypass it.
    """

    _name = "jewelry.repair.order.line.mixin"
    _description = "Repair Order Line Editing Guard"

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = {vals["order_id"] for vals in vals_list if vals.get("order_id")}
        if order_ids:
            self.env["jewelry.repair.order"].browse(order_ids)._check_editable()
        return super().create(vals_list)

    def write(self, vals):
        self.order_id._check_editable()
        if vals.get("order_id"):
            self.env["jewelry.repair.order"].browse(vals["order_id"])._check_editable()
        return super().write(vals)

    def unlink(self):
        self.order_id._check_editable()
        return super().unlink()
