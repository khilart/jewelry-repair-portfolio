from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairServiceLine(models.Model):
    _name = "jewelry.repair.service.line"
    _inherit = "jewelry.repair.order.line.mixin"
    _description = "Jewelry Repair Service Line"
    _order = "sequence, id"

    order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product",
        string="Service Product",
        required=True,
        domain="[('product_tmpl_id.repair_service_ok', '=', True)]",
        context={'repair_service_search': True},
    )
    name = fields.Char(string="Description", required=True)
    operation_id = fields.Many2one(
        "jewelry.repair.operation",
        string="Operation",
        help="Optional production operation generated from this service line.",
    )
    # Compatibility aliases for stale UI/view caches that may still reference removed fields.
    operation_type = fields.Char(
        string="Operation Type (Legacy Alias)",
        compute="_compute_legacy_operation_fields",
        inverse="_inverse_legacy_operation_fields",
    )
    operation_sequence = fields.Integer(
        string="Operation Sequence (Legacy Alias)",
        compute="_compute_legacy_operation_fields",
        inverse="_inverse_legacy_operation_fields",
    )
    order_partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
        readonly=True,
        store=True,
    )
    quantity = fields.Float(string="Qty / Item", default=1.0, required=True)
    batch_quantity = fields.Integer(string="Batch Qty", default=1)
    total_quantity = fields.Float(
        string="Total Qty",
        compute="_compute_total_quantity",
        store=True,
    )
    price_unit = fields.Float(string="Unit Price")
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)
    outsource_cost = fields.Float(string="Outsource Cost", digits=(16, 2))
    base_price = fields.Float(
        string="Base Price",
        digits=(16, 2),
        help="What the service costs the workshop, per unit. Captured when the service is "
             "picked and left untouched when the manager negotiates the selling price.",
    )
    base_amount = fields.Float(
        string="Base Amount",
        compute="_compute_base_amount",
        store=True,
        digits=(16, 2),
        help="Outsource cost when it is set, otherwise base price times total quantity.",
    )
    margin = fields.Float(
        string="Margin",
        compute="_compute_margin",
        store=True,
        digits=(16, 2),
        help="Revenue minus base amount. Negative when the service is sold below its base.",
    )

    @api.depends("quantity", "batch_quantity")
    def _compute_total_quantity(self):
        for line in self:
            line.total_quantity = line.quantity * line.batch_quantity

    @api.depends("operation_id", "operation_id.name", "operation_id.sequence")
    def _compute_legacy_operation_fields(self):
        for line in self:
            line.operation_type = line.operation_id.name if line.operation_id else False
            line.operation_sequence = line.operation_id.sequence if line.operation_id else 0

    def _inverse_legacy_operation_fields(self):
        operation_model = self.env["jewelry.repair.operation"]
        for line in self:
            if line.operation_id:
                continue
            domain = []
            if line.operation_type:
                domain = [("name", "=", line.operation_type)]
            elif line.operation_sequence:
                domain = [("sequence", "=", line.operation_sequence)]
            if domain:
                line.operation_id = operation_model.search(domain, limit=1)

    @api.depends("total_quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.total_quantity * line.price_unit

    @api.depends("outsource_cost", "base_price", "total_quantity")
    def _compute_base_amount(self):
        for line in self:
            if line.outsource_cost:
                # Outsourcing is the real cost, and it is entered per line, not per unit.
                line.base_amount = line.outsource_cost
            else:
                line.base_amount = line.base_price * line.total_quantity

    @api.depends("subtotal", "base_amount")
    def _compute_margin(self):
        for line in self:
            line.margin = line.subtotal - line.base_amount

    @api.model_create_multi
    def create(self, vals_list):
        # Lines built by code or import skip the onchange, and a zero base would report the
        # whole revenue as the manager's markup.
        for vals in vals_list:
            if not vals.get("base_price"):
                vals["base_price"] = vals.get("price_unit", 0.0)
        return super().create(vals_list)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                line.operation_id = False
                line.name = False
                line.price_unit = 0.0
                line.base_price = 0.0
                continue
            product_en = line.product_id.with_context(lang='en_US')
            line.name = product_en.get_product_multiline_description_sale() or product_en.display_name
            line.operation_id = line.product_id.product_tmpl_id.repair_operation_id
            if line.order_id and line.order_id.quantity > 1:
                line.batch_quantity = line.order_id.quantity
            partner_id = line.order_id.partner_id.id
            client_price = False
            if partner_id:
                client_price = self.env["jewelry.repair.client.price"].search([
                    ("partner_id", "=", partner_id),
                    ("product_id", "=", line.product_id.id),
                ], limit=1)
            line.price_unit = client_price.final_price if client_price else line.product_id.lst_price
            line.base_price = line.price_unit

    def action_open_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.order",
            "res_id": self.order_id.id,
            "view_mode": "form",
            "target": "current",
        }


class JewelryRepairClientPrice(models.Model):
    _name = "jewelry.repair.client.price"
    _description = "Client Price"
    _order = "partner_id, product_id"

    partner_id = fields.Many2one("res.partner", string="Client", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one(
        "product.product",
        string="Service",
        required=True,
        ondelete="cascade",
        domain="[('product_tmpl_id.repair_service_ok', '=', True)]",
    )
    base_price = fields.Float(
        string="Base Price",
        related="product_id.lst_price",
        readonly=True,
        digits=(16, 2),
    )
    discount_percent = fields.Float(
        string="Discount / Markup %",
        digits=(16, 2),
        help="Positive value = discount (price reduced). Negative = markup (price increased).",
    )
    custom_price = fields.Float(
        string="Custom Price",
        digits=(16, 2),
        help="If set (> 0), overrides base price and discount.",
    )
    final_price = fields.Float(
        string="Final Price",
        compute="_compute_final_price",
        store=True,
        digits=(16, 2),
    )

    _sql_constraints = [
        ("unique_partner_product", "unique(partner_id, product_id)",
         "A price for this client and service already exists."),
    ]

    @api.depends("base_price", "discount_percent", "custom_price")
    def _compute_final_price(self):
        for rec in self:
            if rec.custom_price > 0:
                rec.final_price = rec.custom_price
            else:
                rec.final_price = rec.base_price * (1.0 - rec.discount_percent / 100.0)


class JewelryRepairApplyMetalRateWizard(models.TransientModel):
    _name = "jewelry.repair.apply.metal.rate.wizard"
    _description = "Apply Metal Rate Datetime Wizard"

    order_id = fields.Many2one("jewelry.repair.order", string="Repair Order", required=True, readonly=True)
    material_line_count = fields.Integer(string="Material Lines", readonly=True)
    metal_rate_at = fields.Datetime(related="order_id.metal_rate_at", string="Metal Rate At", readonly=True)

    def action_confirm(self):
        self.ensure_one()
        self.order_id.action_apply_metal_rate_to_materials()
        return {"type": "ir.actions.act_window_close"}
