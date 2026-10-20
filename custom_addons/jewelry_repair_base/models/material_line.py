from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round


class JewelryRepairMaterialLine(models.Model):
    _name = "jewelry.repair.material.line"
    _inherit = "jewelry.repair.order.line.mixin"
    _description = "Jewelry Repair Material Line"
    _order = "sequence, id"

    order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        required=True,
        ondelete="cascade",
    )
    order_partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
        readonly=True,
        store=True,
    )
    order_operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        string="Order Operation",
        domain="[('order_id', '=', order_id)]",
        ondelete="set null",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product",
        string="Material",
        required=True,
        domain="[('product_tmpl_id.repair_material_ok', '=', True)]",
    )
    quantity = fields.Float(default=1.0, required=True)
    uom_id = fields.Many2one("uom.uom", string="Unit of Measure", required=True)
    weight = fields.Float(string="Weight", digits=(16, 3))
    weight_loss = fields.Float(
        string="Loss Weight",
        digits=(16, 3),
        compute="_compute_weight_loss",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    rate_datetime = fields.Datetime(string="Rate Datetime")
    rate_price_per_gram = fields.Monetary(
        string="Rate Price per Gram",
        currency_field="currency_id",
        copy=False,
    )
    rate_manual = fields.Boolean(
        string="Manual Metal Price",
        default=False,
        copy=False,
        help="Set when the price per gram was entered manually instead of taken from the metal rate.",
    )
    price_unit = fields.Monetary(string="Unit Price", currency_field="currency_id")
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        compute="_compute_subtotal",
        inverse="_inverse_subtotal",
        store=True,
    )
    subtotal_editable = fields.Boolean(compute="_compute_subtotal_editable")
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy")
    description = fields.Text(string="Description")
    include_in_invoice = fields.Boolean(string="Include in Invoice")
    consume_from_stock = fields.Boolean(string="Consume from Stock", default=True)
    return_to_storage = fields.Boolean(string="Return to Storage")
    # source_storage_id / return_storage_id (Many2one to jewelry.metal.storage)
    # are contributed by jewelry_metal_accounting to keep base free of metal deps.
    is_auto_calculated = fields.Boolean(
        string="Auto-Calculated",
        default=False,
        readonly=True,
        copy=False,
        help="Set when this line was created automatically by the metal calculation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            order_operation = self.env["jewelry.repair.order.operation"].browse(vals.get("order_operation_id"))
            if order_operation:
                vals["order_id"] = order_operation.order_id.id

            if vals.get("product_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                vals.setdefault("uom_id", product.uom_id.id)
                vals.setdefault(
                    "description",
                    product.get_product_multiline_description_sale() or product.display_name,
                )
                vals.setdefault(
                    "include_in_invoice",
                    product.product_tmpl_id.repair_material_default_invoice,
                )
                vals.setdefault("price_unit", product.lst_price)
                vals.setdefault(
                    "consume_from_stock",
                    product.product_tmpl_id.repair_material_default_consume,
                )

            if vals.get("order_id") and not vals.get("alloy_id"):
                order = self.env["jewelry.repair.order"].browse(vals["order_id"])
                if order.alloy_id:
                    vals["alloy_id"] = order.alloy_id.id
                vals.setdefault("rate_datetime", order.metal_rate_at)

        lines = super().create(vals_list)
        lines._apply_metal_rate_pricing()
        return lines

    def write(self, vals):
        if self.env.context.get("jewelry_applying_metal_rate"):
            return super().write(vals)
        vals = dict(vals)
        if "rate_price_per_gram" in vals:
            vals.setdefault("rate_manual", True)
        elif {"alloy_id", "rate_datetime"} & set(vals):
            vals.setdefault("rate_manual", False)
        if vals.get("order_operation_id"):
            order_operation = self.env["jewelry.repair.order.operation"].browse(vals["order_operation_id"])
            if order_operation:
                vals["order_id"] = order_operation.order_id.id

        if vals.get("product_id"):
            product = self.env["product.product"].browse(vals["product_id"])
            vals.setdefault("uom_id", product.uom_id.id)
            vals.setdefault(
                "description",
                product.get_product_multiline_description_sale() or product.display_name,
            )
            vals.setdefault(
                "include_in_invoice",
                product.product_tmpl_id.repair_material_default_invoice,
            )
            vals.setdefault("price_unit", product.lst_price)
            vals.setdefault(
                "consume_from_stock",
                product.product_tmpl_id.repair_material_default_consume,
            )
        result = super().write(vals)
        if {"alloy_id", "weight", "quantity", "rate_datetime", "order_id", "product_id", "rate_price_per_gram"} & set(vals):
            self._apply_metal_rate_pricing()
        return result

    @api.onchange("order_id")
    def _onchange_order_id(self):
        for line in self:
            if line.order_id and not line.alloy_id and line.order_id.alloy_id:
                line.alloy_id = line.order_id.alloy_id
            if line.order_id and not line.rate_datetime:
                line.rate_datetime = line.order_id.metal_rate_at

    @api.onchange("order_operation_id")
    def _onchange_order_operation_id(self):
        for line in self:
            if line.order_operation_id:
                line.order_id = line.order_operation_id.order_id
                if not line.alloy_id and line.order_id.alloy_id:
                    line.alloy_id = line.order_id.alloy_id
                if not line.rate_datetime:
                    line.rate_datetime = line.order_id.metal_rate_at

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                line.uom_id = False
                line.description = False
                continue
            template = line.product_id.product_tmpl_id
            line.uom_id = line.product_id.uom_id
            line.description = line.product_id.get_product_multiline_description_sale() or line.product_id.display_name
            line.include_in_invoice = template.repair_material_default_invoice
            line.price_unit = line.product_id.lst_price
            line.consume_from_stock = template.repair_material_default_consume
            if line.order_id and line.order_id.alloy_id and not line.alloy_id:
                line.alloy_id = line.order_id.alloy_id
            if line.order_id and line.order_id.metal_rate_at and not line.rate_datetime:
                line.rate_datetime = line.order_id.metal_rate_at
            line._apply_metal_rate_pricing()

    @api.onchange("weight", "quantity", "product_id")
    def _onchange_metal_rate_inputs(self):
        self._apply_metal_rate_pricing()

    @api.onchange("alloy_id", "rate_datetime")
    def _onchange_metal_rate_source(self):
        for line in self:
            line.rate_manual = False
        self._apply_metal_rate_pricing()

    @api.onchange("rate_price_per_gram")
    def _onchange_rate_price_per_gram(self):
        for line in self:
            if not line._is_metal_priced_line():
                continue
            rate = line._get_applicable_metal_rate()
            market_price = rate.price_per_gram if rate else 0.0
            line.rate_manual = float_compare(
                line.rate_price_per_gram,
                market_price,
                precision_rounding=line.currency_id.rounding or 0.01,
            ) != 0
        self._apply_metal_rate_pricing()

    @api.depends("weight", "product_id", "product_id.product_tmpl_id.repair_material_return_loss_percent")
    def _compute_weight_loss(self):
        for line in self:
            percent = line.product_id.product_tmpl_id.repair_material_return_loss_percent or 0.0
            line.weight_loss = (line.weight or 0.0) * percent / 100.0

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    def _inverse_subtotal(self):
        for line in self:
            qty = line.quantity or 1.0
            line.price_unit = line.subtotal / qty

    @api.depends_context("uid")
    def _compute_subtotal_editable(self):
        is_manager = self.env.user.has_group(
            "jewelry_repair_base.group_jewelry_repair_manager"
        )
        for line in self:
            line.subtotal_editable = is_manager

    def _is_metal_priced_line(self):
        self.ensure_one()
        return bool(self.alloy_id and self.weight)

    def _get_effective_rate_datetime(self):
        self.ensure_one()
        return self.rate_datetime or self.order_id.metal_rate_at

    def _get_weight_for_pricing(self):
        self.ensure_one()
        return (self.weight or 0.0) + (self.weight_loss or 0.0)

    def _get_applicable_metal_rate(self):
        self.ensure_one()
        if not self.alloy_id:
            return self.env["jewelry.metal.rate"].browse()
        return self.env["jewelry.metal.rate"]._get_latest_rate(
            self.alloy_id.metal_id,
            self._get_effective_rate_datetime(),
            self.env.company,
        )

    def _prepare_metal_rate_pricing_vals(self):
        self.ensure_one()
        if not self._is_metal_priced_line():
            return {}

        if self.rate_manual:
            price_per_gram = self.rate_price_per_gram
        else:
            rate = self._get_applicable_metal_rate()
            if not rate:
                return {
                    "rate_price_per_gram": 0.0,
                    "rate_manual": False,
                    "price_unit": 0.0,
                }
            price_per_gram = rate.price_per_gram

        total_price = price_per_gram * (self.alloy_id.purity or 0.0) * self._get_weight_for_pricing()
        quantity = self.quantity or 0.0
        unit_price = total_price / quantity if quantity else total_price
        # The workshop quotes metal in whole units: rounding the unit price keeps
        # the subtotal whole too, and it is the unit price that reaches the invoice.
        unit_price = float_round(unit_price, precision_digits=0)
        return {
            "rate_price_per_gram": price_per_gram,
            "rate_manual": self.rate_manual,
            "price_unit": unit_price,
        }

    def _apply_metal_rate_pricing(self):
        for line in self:
            vals = line._prepare_metal_rate_pricing_vals()
            if vals:
                line.with_context(jewelry_applying_metal_rate=True).update(vals)

    @api.constrains("order_id", "order_operation_id")
    def _check_operation_belongs_to_order(self):
        for line in self:
            if line.order_operation_id and line.order_operation_id.order_id != line.order_id:
                raise ValidationError(_("The selected operation must belong to the same repair order."))

    @api.constrains("product_id", "weight")
    def _check_required_weight(self):
        for line in self:
            if line.product_id.product_tmpl_id.repair_material_requires_weight and line.weight <= 0:
                raise ValidationError(_("Weight is required for the selected repair material."))

    @api.constrains("alloy_id", "weight", "rate_datetime", "order_id")
    def _check_metal_rate_exists(self):
        for line in self.filtered(lambda candidate: candidate._is_metal_priced_line() and not candidate.rate_manual):
            if not line._get_effective_rate_datetime():
                raise ValidationError(_("Set a metal rate datetime on the order or material line before pricing metallic materials."))
            if not line._get_applicable_metal_rate():
                raise ValidationError(_("No metal rate was found for the selected alloy and rate datetime."))
