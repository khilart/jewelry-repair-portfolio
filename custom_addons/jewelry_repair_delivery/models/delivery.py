from odoo import _, api, fields, models
from odoo.exceptions import UserError


class JewelryRepairDelivery(models.Model):
    _name = "jewelry.repair.delivery"
    _description = "Jewelry Repair Delivery"
    _order = "delivery_date desc, id desc"

    name = fields.Char(
        string="Delivery Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    delivery_date = fields.Date(required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    order_ids = fields.Many2many(
        "jewelry.repair.order",
        "jewelry_repair_delivery_order_rel",
        "delivery_id",
        "order_id",
        string="Orders",
    )
    line_ids = fields.One2many(
        "jewelry.repair.delivery.line",
        "delivery_id",
        string="Delivery Lines",
    )
    confirmed_line_ids = fields.Many2many(
        "jewelry.repair.delivery.line",
        compute="_compute_confirmed_line_ids",
        string="Confirmed Delivery Lines",
    )
    notes = fields.Text()
    order_count = fields.Integer(compute="_compute_order_count")
    selected_order_count = fields.Integer(compute="_compute_selection_totals")
    selected_amount_total = fields.Monetary(
        string="Selected Total",
        currency_field="currency_id",
        compute="_compute_selection_totals",
    )
    available_order_count = fields.Integer(compute="_compute_selection_totals")
    metal_price_per_gram = fields.Monetary(
        string="Fine Metal Price per Gram",
        currency_field="currency_id",
        copy=False,
        help="Price per gram of fine metal applied to the material lines of the selected orders.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
    )

    @api.depends("partner_id")
    def _compute_currency_id(self):
        for delivery in self:
            delivery.currency_id = self.env.company.currency_id

    @api.depends("order_ids")
    def _compute_order_count(self):
        for delivery in self:
            delivery.order_count = len(delivery.order_ids)

    @api.depends("order_ids.amount_total", "line_ids")
    def _compute_selection_totals(self):
        for delivery in self:
            report_orders = delivery.order_ids
            delivery.selected_order_count = len(report_orders)
            delivery.selected_amount_total = sum(report_orders.mapped("amount_total"))
            delivery.available_order_count = len(delivery.line_ids)

    @api.depends("order_ids", "line_ids.order_id")
    def _compute_confirmed_line_ids(self):
        for delivery in self:
            delivery.confirmed_line_ids = delivery.line_ids.filtered(lambda line: line.order_id in delivery.order_ids)

    def _sync_order_ids_from_selected_lines(self):
        for delivery in self:
            selected_orders = delivery.line_ids.filtered(lambda line: line.selected and line.order_id).mapped("order_id")
            delivery.order_ids = [(6, 0, selected_orders.ids)]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = sequence.next_by_code("jewelry.repair.delivery") or _("New")
        deliveries = super().create(vals_list)
        deliveries.filtered("partner_id")._sync_candidate_lines()
        return deliveries

    def write(self, vals):
        if self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_director"):
            raise UserError(_("Directors have read-only access. Contact a manager to make changes."))
        result = super().write(vals)
        if "line_ids" in vals:
            self.filtered(lambda delivery: delivery.state == "draft")._sync_order_ids_from_selected_lines()
        if {"partner_id", "state"} & set(vals):
            self.filtered(lambda delivery: delivery.state == "draft")._sync_candidate_lines()
        return result

    def _get_candidate_orders(self):
        self.ensure_one()
        if not self.partner_id:
            return self.env["jewelry.repair.order"]
        return self.env["jewelry.repair.order"].search(
            [
                ("partner_id", "=", self.partner_id.id),
                ("state", "=", "ready"),
                ("delivery_id", "=", False),
                ("ready_accepted_by_manager", "=", True),
            ],
            order="deadline_date, id",
        )

    def _sync_candidate_lines(self):
        for delivery in self:
            if delivery.state != "draft":
                continue
            if not delivery.partner_id:
                delivery.line_ids = [(5, 0, 0)]
                delivery.order_ids = [(5, 0, 0)]
                continue
            candidate_orders = delivery._get_candidate_orders()
            selected_order_ids = set(delivery.order_ids.ids)
            selected_order_ids &= set(candidate_orders.ids)
            commands = [(5, 0, 0)]
            for order in candidate_orders:
                commands.append(
                    (
                        0,
                        0,
                        {
                            "order_id": order.id,
                            "selected": order.id in selected_order_ids,
                        },
                    )
                )
            delivery.line_ids = commands
            delivery.order_ids = [(6, 0, list(selected_order_ids))]

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for delivery in self:
            if not delivery.partner_id:
                delivery.line_ids = [(5, 0, 0)]
                delivery.order_ids = [(5, 0, 0)]
                continue
            delivery._sync_candidate_lines()

    @api.onchange("line_ids", "line_ids.selected")
    def _onchange_line_ids(self):
        self._sync_order_ids_from_selected_lines()

    def action_select_all_orders(self):
        for delivery in self.filtered(lambda record: record.state == "draft"):
            delivery.line_ids.write({"selected": True})
            delivery._sync_order_ids_from_selected_lines()

    def action_clear_selected_orders(self):
        for delivery in self.filtered(lambda record: record.state == "draft"):
            delivery.line_ids.write({"selected": False})
            delivery._sync_order_ids_from_selected_lines()

    def action_apply_metal_price(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("The metal price can be recalculated only while the delivery is a draft."))
        if not self.metal_price_per_gram:
            raise UserError(_("Set the fine metal price per gram before recalculating."))
        if not self.order_ids:
            raise UserError(_("Select at least one repair order before recalculating the metal price."))
        material_lines = self.order_ids.material_line_ids.filtered(
            lambda line: line._is_metal_priced_line()
        )
        if not material_lines:
            raise UserError(_("The selected orders have no metal material lines to update."))
        material_lines.write({"rate_price_per_gram": self.metal_price_per_gram})

    def action_refresh_candidates(self):
        self.filtered(lambda delivery: delivery.state == "draft")._sync_candidate_lines()

    def action_print_delivery(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_delivery.report_jewelry_repair_delivery_document/%s" % self.id,
            "target": "new",
        }

    def action_print_delivery_en(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_delivery.report_jewelry_repair_delivery_document/%s?lang=en_US" % self.id,
            "target": "new",
        }

    def action_confirm(self):
        for delivery in self:
            selected_orders = delivery.order_ids
            if not selected_orders:
                raise UserError(_("Add at least one repair order before confirming the delivery."))

            invalid_orders = selected_orders.filtered(
                lambda order: order.partner_id != delivery.partner_id
                or order.state != "ready"
                or order.delivery_id
                or not order.ready_accepted_by_manager
            )
            if invalid_orders:
                raise UserError(
                    _(
                        "All selected orders must belong to the same customer, be in Ready status, be accepted by the manager, and not be delivered yet."
                    )
                )
            delivery.order_ids = [(6, 0, selected_orders.ids)]
            delivery.order_ids.write(
                {
                    "state": "delivered",
                    "delivery_id": delivery.id,
                    "delivery_date": delivery.delivery_date,
                    "current_holder_user_id": False,
                    "current_holder_role": "customer",
                    "current_location_type": "delivered",
                    "last_move_at": fields.Datetime.now(),
                }
            )
            delivery.state = "done"

    def action_cancel(self):
        for delivery in self:
            if delivery.state == "done":
                delivery.order_ids.filtered(lambda order: order.delivery_id == delivery).write(
                    {
                        "state": "ready",
                        "delivery_id": False,
                        "delivery_date": False,
                        "current_location_type": "ready_for_delivery",
                        "last_move_at": fields.Datetime.now(),
                    }
                )
            delivery.state = "cancel"

    def action_reset_to_draft(self):
        for delivery in self:
            if delivery.state == "done":
                raise UserError(_("Cancel the confirmed delivery before resetting it to draft."))
            delivery.state = "draft"
            delivery._sync_candidate_lines()

    def _get_report_orders(self):
        self.ensure_one()
        return self.order_ids

    def _get_delivery_service_summary(self):
        self.ensure_one()
        summary = {}
        for order in self._get_report_orders():
            for line in order.service_line_ids:
                en_name = (
                    line.product_id.with_context(lang="en_US").name
                    if line.product_id
                    else line.name
                )
                key = (line.product_id.id, en_name, line.price_unit)
                if key not in summary:
                    summary[key] = {
                        "name": en_name,
                        "quantity": 0.0,
                        "subtotal": 0.0,
                    }
                summary[key]["quantity"] += line.total_quantity
                summary[key]["subtotal"] += line.subtotal
        return sorted(summary.values(), key=lambda item: item["name"])

    def _get_delivery_service_summary_grouped(self):
        self.ensure_one()
        summary = {}
        new_mfg_total = 0.0
        new_mfg_count = 0
        for order in self._get_report_orders():
            if order.new_product_manufacturing:
                new_mfg_count += 1
                new_mfg_total += sum(line.subtotal for line in order.service_line_ids)
            else:
                for line in order.service_line_ids:
                    en_name = (
                        line.product_id.with_context(lang="en_US").name
                        if line.product_id
                        else line.name
                    )
                    key = (line.product_id.id, en_name, line.price_unit)
                    if key not in summary:
                        summary[key] = {"name": en_name, "quantity": 0.0, "subtotal": 0.0}
                    summary[key]["quantity"] += line.total_quantity
                    summary[key]["subtotal"] += line.subtotal
        result = sorted(summary.values(), key=lambda item: item["name"])
        if new_mfg_count:
            result.append({
                "name": "Manufacture of New Item",
                "quantity": float(new_mfg_count),
                "subtotal": new_mfg_total,
            })
        return result

    def action_print_delivery_grouped(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_delivery.report_jewelry_repair_delivery_document_grouped/%s" % self.id,
            "target": "new",
        }

    def _get_delivery_material_summary(self):
        self.ensure_one()
        summary = {}
        for order in self._get_report_orders():
            for line in order.material_line_ids.filtered("include_in_invoice"):
                key = (
                    line.product_id.id,
                    line.alloy_id.id if line.alloy_id else 0,
                    line.description or line.product_id.display_name,
                    line.price_unit,
                )
                if key not in summary:
                    summary[key] = {
                        "name": line.description or line.product_id.display_name,
                        "alloy_name": line.alloy_id.display_name if line.alloy_id else "",
                        "quantity": 0.0,
                        "weight": 0.0,
                        "subtotal": 0.0,
                    }
                summary[key]["quantity"] += line.quantity
                summary[key]["weight"] += line.weight or 0.0
                summary[key]["subtotal"] += line.subtotal
        return sorted(summary.values(), key=lambda item: (item["name"], item["alloy_name"]))


class JewelryRepairDeliveryLine(models.Model):
    _name = "jewelry.repair.delivery.line"
    _description = "Jewelry Repair Delivery Line"
    _order = "selected desc, order_deadline_date, id"

    delivery_id = fields.Many2one(
        "jewelry.repair.delivery",
        string="Delivery",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Deliver", default=False)
    order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        required=True,
        ondelete="cascade",
    )
    order_name = fields.Char(related="order_id.name", string="Order Number", readonly=True)
    order_item_image = fields.Image(related="order_id.item_image_128", string="Item Photo", readonly=True)
    order_amount_total = fields.Monetary(
        related="order_id.amount_total",
        string="Order Total",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    order_item_type_id = fields.Many2one(related="order_id.item_type_id", string="Item Type", readonly=True)
    order_deadline_date = fields.Datetime(related="order_id.deadline_date", string="Deadline", readonly=True)
    order_description = fields.Text(related="order_id.description", string="Description", readonly=True)
    order_state = fields.Selection(related="order_id.state", string="Order State", readonly=True)

    _sql_constraints = [
        ("jewelry_repair_delivery_line_order_unique", "unique(delivery_id, order_id)", "Each order can appear only once in a delivery draft."),
    ]



class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    delivery_id = fields.Many2one(
        "jewelry.repair.delivery",
        string="Delivery Document",
        readonly=True,
        copy=False,
    )
    delivery_date = fields.Date(readonly=True, copy=False)

    def action_mark_ready(self):
        result = super().action_mark_ready()
        self.write({"delivery_id": False, "delivery_date": False})
        return result

    def _get_workflow_fields(self):
        return super()._get_workflow_fields() | {"delivery_id", "delivery_date"}

    def action_open_delivery(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery"),
            "res_model": "jewelry.repair.delivery",
            "res_id": self.delivery_id.id,
            "view_mode": "form",
        }
