from odoo import _, fields, models
from odoo.exceptions import UserError


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    model_3d_id = fields.Many2one(
        "jewelry.model.3d",
        string="3D Model",
        copy=False,
    )

    def action_load_from_model(self):
        self.ensure_one()
        if not self.model_3d_id:
            raise UserError(_("Select a 3D model first."))

        model = self.model_3d_id

        for tmpl in model.service_template_ids:
            self.env["jewelry.repair.service.line"].create({
                "order_id": self.id,
                "product_id": tmpl.product_id.id,
                "name": tmpl.product_id.name,
                "quantity": tmpl.quantity,
                "price_unit": tmpl.price_unit,
            })

        for tmpl in model.material_template_ids:
            product = tmpl.alloy_id.effective_material_product_id
            if not product:
                continue
            self.env["jewelry.repair.material.line"].create({
                "order_id": self.id,
                "product_id": product.id,
                "alloy_id": tmpl.alloy_id.id,
                "weight": tmpl.weight or 0.0,
                "quantity": 1.0,
                "uom_id": product.uom_id.id,
                "include_in_invoice": True,
            })

        for seat in model.stone_seat_ids.filtered("gem_type_id"):
            self.env["jewelry.repair.gem.line"].create({
                "order_id": self.id,
                "gem_type_id": seat.gem_type_id.id,
                "cut_shape": seat.cut_shape or False,
                "standard_size_id": seat.standard_size_id.id if seat.standard_size_id else False,
                "quantity": seat.count,
            })
