from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .constants import GEM_CUT_SHAPES


class JewelryRepairOrder(models.Model):
    _name = "jewelry.repair.order"
    _inherit = ["mail.thread"]
    _description = "Jewelry Repair Order"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Order Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        domain=[("customer_rank", ">", 0)],
    )
    item_type_id = fields.Many2one(
        "jewelry.repair.item.type",
        string="Item Type",
        required=True,
    )
    item_size_id = fields.Many2one(
        "jewelry.repair.item.size",
        string="Size",
        domain="[('item_type_id', '=', item_type_id)]",
    )
    quantity = fields.Integer(default=1, required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id.id,
        readonly=True,
    )
    new_product_manufacturing = fields.Boolean(string="New Product Manufacturing")
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy")
    metal_id = fields.Many2one(
        "jewelry.metal",
        string="Metal",
        related="alloy_id.metal_id",
        store=True,
        readonly=True,
    )
    received_weight = fields.Float(string="Received Weight", digits=(16, 3))
    delivered_weight = fields.Float(string="Delivered Weight", digits=(16, 3))
    weight_delta = fields.Float(
        string="Weight Delta",
        compute="_compute_weight_metrics",
        store=True,
        digits=(16, 3),
    )
    fine_weight_received = fields.Float(
        string="Fine Weight Received",
        compute="_compute_weight_metrics",
        store=True,
        digits=(16, 3),
    )
    fine_weight_delivered = fields.Float(
        string="Fine Weight Delivered",
        compute="_compute_weight_metrics",
        store=True,
        digits=(16, 3),
    )
    external_doc_number = fields.Char(string="External Document Number")
    item_image = fields.Image(
        string="Item Photo",
        max_width=2160,
        max_height=3840,
    )
    item_image_128 = fields.Image(
        string="Item Photo Thumbnail",
        related="item_image",
        max_width=128,
        max_height=128,
        store=True,
        attachment=False,
    )
    item_image_upload = fields.Binary(
        string="Upload Item Photo",
        compute="_compute_item_image_upload",
        inverse="_inverse_item_image_upload",
    )
    description = fields.Text(string="Item Description")
    received_date = fields.Datetime(
        string="Received At",
        required=True,
        default=fields.Datetime.now,
    )
    deadline_date = fields.Datetime(
        string="Deadline",
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
    )
    metal_rate_at = fields.Datetime(
        string="Metal Rate At",
        default=fields.Datetime.now,
    )
    earliest_ready_date = fields.Datetime(
        string="Earliest Possible At",
        compute="_compute_earliest_ready_date",
    )
    deadline_warning = fields.Char(
        string="Deadline Warning",
        compute="_compute_deadline_warning",
    )
    amount_total = fields.Monetary(
        string="Order Total",
        currency_field="currency_id",
        compute="_compute_order_totals",
        store=True,
        compute_sudo=True,
    )
    total_duration_minutes = fields.Float(
        string="Total Work Minutes",
        compute="_compute_order_totals",
        store=True,
        compute_sudo=True,
    )
    total_duration_display = fields.Char(
        string="Expected Work Time",
        compute="_compute_order_totals",
        store=True,
        compute_sudo=True,
    )
    service_product_count = fields.Integer(
        compute="_compute_catalog_counts",
        string="Repair Service Products",
    )
    operation_catalog_count = fields.Integer(
        compute="_compute_catalog_counts",
        string="Operations Catalog",
    )
    work_operation_count = fields.Integer(
        compute="_compute_catalog_counts",
        string="Work Operations",
    )
    current_holder_user_id = fields.Many2one(
        "res.users",
        string="Current Holder",
        readonly=True,
        copy=False,
    )
    current_holder_role = fields.Selection(
        [
            ("receptionist", "Receptionist"),
            ("master", "Master"),
            ("manager", "Manager"),
            ("customer", "Customer"),
        ],
        string="Current Holder Role",
        readonly=True,
        copy=False,
    )
    current_location_type = fields.Selection(
        [
            ("reception", "Reception"),
            ("in_work", "In Work"),
            ("ready_for_delivery", "Ready For Delivery"),
            ("delivered", "Delivered"),
        ],
        string="Current Location",
        readonly=True,
        copy=False,
    )
    last_move_at = fields.Datetime(string="Last Move At", readonly=True, copy=False)
    next_holder_user_id = fields.Many2one(
        "res.users",
        string="Next Holder",
        compute="_compute_next_holder_user_id",
    )
    ready_accepted_by_manager = fields.Boolean(string="Ready Accepted By Manager", readonly=True, copy=False)
    ready_accepted_at = fields.Datetime(string="Ready Accepted At", readonly=True, copy=False)
    amendment_open = fields.Boolean(string="Unlocked For Editing", readonly=True, copy=False)
    amendment_reason = fields.Char(string="Unlock Reason", readonly=True, copy=False)
    amendment_user_id = fields.Many2one("res.users", string="Unlocked By", readonly=True, copy=False)
    amendment_at = fields.Datetime(string="Unlocked At", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("ready", "Ready"),
            ("delivered", "Delivered"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        required=True,
        default="draft",
    )
    notes = fields.Text(string="Internal Notes")
    active = fields.Boolean(default=True)
    service_line_ids = fields.One2many(
        "jewelry.repair.service.line",
        "order_id",
        string="Services",
    )
    material_line_ids = fields.One2many(
        "jewelry.repair.material.line",
        "order_id",
        string="Materials",
    )
    gem_line_ids = fields.One2many(
        "jewelry.repair.gem.line",
        "order_id",
        string="Stones",
    )
    certificate_numbers = fields.Char(
        string="Certificate Numbers",
        compute="_compute_certificate_numbers",
        store=True,
    )
    gem_weight_total_g = fields.Float(
        string="Total Gem Weight (g)",
        compute="_compute_gem_weight_total_g",
        store=True,
        digits=(16, 3),
    )
    received_with_gems_g = fields.Float(
        string="Received + Gems (g)",
        compute="_compute_gem_weight_total_g",
        store=True,
        digits=(16, 3),
    )
    metal_delivered_weight = fields.Float(
        string="Metal Delivered Weight",
        compute="_compute_metal_delivered_weight",
        store=True,
        digits=(16, 3),
    )
    order_operation_ids = fields.One2many(
        "jewelry.repair.order.operation",
        "order_id",
        string="Order Operations",
    )
    area_loss_ids = fields.One2many(
        "jewelry.order.area.loss",
        "order_id",
        string="Area Losses",
    )
    total_metal_loss_percent = fields.Float(
        string="Total Metal Loss %",
        digits=(16, 2),
        compute="_compute_total_metal_loss_percent",
        store=True,
    )
    weight_tracking_enabled = fields.Boolean(
        compute="_compute_weight_tracking_enabled",
        string="Weight Tracking Enabled",
    )
    # Compatibility alias for stale UI/view caches that may still reference the old field name.
    operation_ids = fields.One2many(
        "jewelry.repair.order.operation",
        "order_id",
        string="Operations (Legacy Alias)",
    )

    _work_periods = (
        (time(9, 0), time(13, 0)),
        (time(14, 0), time(18, 0)),
    )

    def _next_work_moment(self, moment):
        current = moment
        while True:
            current_time = current.time()
            for period_start, period_end in self._work_periods:
                if current_time < period_start:
                    return datetime.combine(current.date(), period_start)
                if period_start <= current_time < period_end:
                    return current
            current = datetime.combine(current.date() + timedelta(days=1), self._work_periods[0][0])

    def _add_work_minutes(self, start_at, duration_minutes):
        current = self._next_work_moment(start_at)
        remaining_minutes = max(duration_minutes, 0.0)

        while remaining_minutes > 0:
            current = self._next_work_moment(current)
            for period_start, period_end in self._work_periods:
                period_start_dt = datetime.combine(current.date(), period_start)
                period_end_dt = datetime.combine(current.date(), period_end)
                if current >= period_end_dt:
                    continue
                if current < period_start_dt:
                    current = period_start_dt
                available_minutes = (period_end_dt - current).total_seconds() / 60.0
                if remaining_minutes <= available_minutes:
                    return current + timedelta(minutes=remaining_minutes)
                remaining_minutes -= available_minutes
                current = period_end_dt

            current = datetime.combine(current.date() + timedelta(days=1), self._work_periods[0][0])

        return current

    def _compute_catalog_counts(self):
        service_product_count = self.env["product.template"].search_count([("repair_service_ok", "=", True)])
        operation_catalog_count = self.env["jewelry.repair.operation"].search_count([])
        for order in self:
            order.service_product_count = service_product_count
            order.operation_catalog_count = operation_catalog_count
            order.work_operation_count = len(order.order_operation_ids)

    def _get_holder_role_for_user(self, user):
        user.ensure_one()
        if user.has_group("base.group_system") or user.has_group("jewelry_repair_base.group_jewelry_repair_manager"):
            return "manager"
        if user.has_group("jewelry_repair_base.group_jewelry_repair_receptionist"):
            return "receptionist"
        if user.has_group("jewelry_repair_base.group_jewelry_repair_master"):
            return "master"
        return "receptionist"

    @api.depends("gem_line_ids.certificate_id.name")
    def _compute_certificate_numbers(self):
        for order in self:
            names = order.gem_line_ids.filtered("certificate_id").mapped("certificate_id.name")
            order.certificate_numbers = " ".join(names) if names else False

    @api.depends("gem_line_ids.total_weight_g", "received_weight")
    def _compute_gem_weight_total_g(self):
        for order in self:
            order.gem_weight_total_g = sum(order.gem_line_ids.mapped("total_weight_g"))
            order.received_with_gems_g = (order.received_weight or 0.0) + order.gem_weight_total_g

    @api.depends("delivered_weight", "gem_weight_total_g")
    def _compute_metal_delivered_weight(self):
        for order in self:
            order.metal_delivered_weight = (order.delivered_weight or 0.0) - order.gem_weight_total_g

    @api.depends("order_operation_ids.state", "order_operation_ids.assigned_user_id", "order_operation_ids.executor_id")
    def _compute_next_holder_user_id(self):
        for order in self:
            next_op = order.order_operation_ids.filtered(
                lambda o: o.state not in ("done", "cancel")
            )[:1]
            if next_op:
                order.next_holder_user_id = next_op.assigned_user_id or next_op.executor_id.user_id
            else:
                order.next_holder_user_id = False

    def _set_current_holder(self, user=False, location_type=False):
        values = {
            "current_holder_user_id": user.id if user else False,
            "current_holder_role": self._get_holder_role_for_user(user) if user else False,
            "current_location_type": location_type,
            "last_move_at": fields.Datetime.now(),
        }
        self.write(values)

    @api.depends("alloy_id", "alloy_id.purity", "received_weight", "delivered_weight")
    def _compute_weight_metrics(self):
        for order in self:
            purity = order.alloy_id.purity or 0.0
            order.weight_delta = (order.delivered_weight or 0.0) - (order.received_weight or 0.0)
            order.fine_weight_received = (order.received_weight or 0.0) * purity
            order.fine_weight_delivered = (order.delivered_weight or 0.0) * purity

    @api.depends("item_image")
    def _compute_item_image_upload(self):
        for order in self:
            order.item_image_upload = order.item_image

    def _inverse_item_image_upload(self):
        for order in self:
            order.item_image = order.item_image_upload

    @api.onchange("metal_rate_at")
    def _onchange_metal_rate_at(self):
        for order in self:
            order.material_line_ids.filtered(lambda line: not line.rate_datetime)._apply_metal_rate_pricing()

    @api.onchange("quantity")
    def _onchange_quantity(self):
        for order in self:
            order.service_line_ids.update({"batch_quantity": order.quantity})

    def _get_workflow_fields(self):
        """Fields whose change is not an edit of the order content.

        Extended by the delivery and billing modules with their own workflow fields.
        """
        return {
            "state",
            "current_holder_user_id",
            "current_holder_role",
            "current_location_type",
            "last_move_at",
            "ready_accepted_by_manager",
            "ready_accepted_at",
            "amendment_open",
            "amendment_reason",
            "amendment_user_id",
            "amendment_at",
        }

    def _check_editable(self):
        """Raise unless the content of these orders may be changed.

        Called from every entry point that changes the order content, not only from
        ``write``, so that writing directly to the order lines cannot bypass it.
        """
        if self.env.user.has_group("base.group_system"):
            return
        locked = self.filtered(
            lambda order: order.state == "delivered" and not order.amendment_open
        )
        if locked:
            raise UserError(
                _('Delivered repair orders are read-only. Use "Unlock for Editing" to correct them.')
            )

    def _amendment_documents(self):
        """Records that will be cancelled to unlock the order, in cancellation order.

        Extended by the billing module.
        """
        self.ensure_one()
        return []

    def _amendment_rollback(self):
        """Cancel the documents that block editing of the order.

        Extended by the billing module.
        """
        self.ensure_one()
        return

    def _amendment_payment_warning(self):
        """Warning shown before unlocking, or an empty value when there is nothing to warn about.

        Extended by the billing module.
        """
        return False

    def action_open_amendment(self):
        self.ensure_one()
        is_manager = self.env.user.has_group(
            "jewelry_repair_base.group_jewelry_repair_manager"
        ) or self.env.user.has_group("base.group_system")
        if not is_manager:
            raise UserError(_("Only a manager can unlock a delivered order for editing."))
        if self.state != "delivered":
            raise UserError(_("Only delivered repair orders need to be unlocked for editing."))
        if self.amendment_open:
            raise UserError(_("The order is already unlocked for editing."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Unlock for Editing"),
            "res_model": "jewelry.repair.amendment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def _open_amendment(self, reason):
        self.ensure_one()
        # Collected before the rollback: cancelling clears the links to these documents,
        # and a draft invoice is deleted outright, so its name has to be read now.
        documents = self._amendment_documents()
        document_names = [document.display_name for document in documents]
        self._amendment_rollback()
        self.write(
            {
                "amendment_open": True,
                "amendment_reason": reason,
                "amendment_user_id": self.env.user.id,
                "amendment_at": fields.Datetime.now(),
            }
        )
        self._amendment_log(reason, document_names, documents)

    def _close_amendment(self):
        """Leave the editing mode and refresh what the correction may have invalidated.

        Extended by the billing module.
        """
        self.write(
            {
                "amendment_open": False,
                "amendment_reason": False,
                "amendment_user_id": False,
                "amendment_at": False,
            }
        )
        # Area losses are stored rows, and nothing rebuilds them when material or gem
        # lines change on a delivered order — only a change of delivered_weight does.
        self._compute_area_losses()

    def _amendment_log(self, reason, document_names, documents):
        self.ensure_one()
        body = _("Unlocked for editing. Reason: %s") % reason
        if document_names:
            body += " " + (_("Cancelled documents: %s") % ", ".join(document_names))
        # _message_log, not message_post: an internal log note that needs no sender address.
        self._message_log(body=body)
        note = _(
            "Cancelled because repair order %(order)s was unlocked for editing. Reason: %(reason)s"
        ) % {"order": self.name, "reason": reason}
        for document in documents:
            if document.exists():
                document.sudo()._message_log(body=note)

    def write(self, vals):
        if self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_director"):
            raise UserError(_("Directors have read-only access. Contact a manager to make changes."))
        if set(vals) - self._get_workflow_fields():
            self._check_editable()
        result = super().write(vals)
        if "metal_rate_at" in vals:
            self.mapped("material_line_ids").filtered(lambda line: not line.rate_datetime)._apply_metal_rate_pricing()
        if "delivered_weight" in vals:
            orders = self.filtered(lambda o: o.state in ("ready", "delivered"))
            if orders:
                orders._compute_area_losses()
        if vals.get("state") == "ready":
            self._compute_area_losses()
        return result

    @api.depends(
        "service_line_ids.quantity",
        "service_line_ids.price_unit",
        "service_line_ids.subtotal",
        "material_line_ids.include_in_invoice",
        "material_line_ids.subtotal",
        "gem_line_ids.include_in_invoice",
        "gem_line_ids.subtotal",
        "service_line_ids.operation_id",
        "service_line_ids.operation_id.duration_minutes",
    )
    def _compute_order_totals(self):
        for order in self:
            total_minutes = sum(
                line.quantity * line.operation_id.duration_minutes
                for line in order.service_line_ids
                if line.operation_id and line.quantity
            )
            order.amount_total = (
                sum(order.service_line_ids.mapped("subtotal"))
                + sum(order.material_line_ids.filtered("include_in_invoice").mapped("subtotal"))
                + sum(order.gem_line_ids.filtered("include_in_invoice").mapped("subtotal"))
            )
            order.total_duration_minutes = total_minutes

            total_minutes_rounded = int(round(total_minutes))
            days, remainder = divmod(total_minutes_rounded, 8 * 60)
            hours, minutes = divmod(remainder, 60)
            parts = []
            if days:
                parts.append(_("%s d") % days)
            if hours:
                parts.append(_("%s h") % hours)
            if minutes or not parts:
                parts.append(_("%s m") % minutes)
            order.total_duration_display = " ".join(parts)

    @api.depends(
        "received_date",
        "total_duration_minutes",
    )
    def _compute_earliest_ready_date(self):
        for order in self:
            if not order.received_date:
                order.earliest_ready_date = False
                continue

            received_at = fields.Datetime.to_datetime(order.received_date)
            order.earliest_ready_date = order._add_work_minutes(received_at, order.total_duration_minutes)

    @api.depends("deadline_date", "earliest_ready_date")
    def _compute_deadline_warning(self):
        for order in self:
            if order.deadline_date and order.earliest_ready_date:
                deadline_at = fields.Datetime.to_datetime(order.deadline_date)
                if deadline_at < fields.Datetime.to_datetime(order.earliest_ready_date):
                    order.deadline_warning = _(
                        "Requested deadline is earlier than the estimated minimum completion time: %s"
                    ) % fields.Datetime.to_string(order.earliest_ready_date)
                    continue
            order.deadline_warning = False

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = sequence.next_by_code("jewelry.repair.order") or _("New")
        orders = super().create(vals_list)
        for order in orders.filtered(lambda rec: not rec.current_holder_user_id):
            order._set_current_holder(order.create_uid, "reception")
        return orders

    def _get_product_price_for_partner(self, product, partner_id):
        """Return client-specific price if configured, otherwise lst_price."""
        if partner_id:
            client_price = self.env["jewelry.repair.client.price"].search([
                ("partner_id", "=", partner_id),
                ("product_id", "=", product.id),
            ], limit=1)
            if client_price:
                return client_price.final_price
        return product.lst_price

    def action_generate_setting_services(self):
        self.ensure_one()
        if not self.gem_line_ids:
            raise UserError(_("No stones added to the order."))

        # Group stone lines by matching setting rule
        rule_lines = {}
        unmatched = []
        for gem_line in self.gem_line_ids:
            rules = gem_line.gem_type_id.setting_rule_ids.filtered(
                lambda r: r.weight_ct_from <= gem_line.weight_ct and
                (r.weight_ct_to == 0 or gem_line.weight_ct < r.weight_ct_to)
            )
            if not rules:
                unmatched.append(f"{gem_line.gem_type_id.name} {gem_line.weight_ct:g} ct")
                continue
            rule = rules[0]
            rule_lines.setdefault(rule, []).append(gem_line)

        if unmatched:
            raise UserError(
                _("No setting rule found for: %s.\nPlease configure setting rules on the gem type.") % ", ".join(unmatched)
            )

        ServiceLine = self.env["jewelry.repair.service.line"]
        partner_id = self.partner_id.id
        for rule, lines in rule_lines.items():
            product = rule.service_product_id
            pricing_type = product.product_tmpl_id.gem_pricing_type
            operation_id = product.product_tmpl_id.repair_operation_id.id or False
            base_price = self._get_product_price_for_partner(product, partner_id)

            if pricing_type == "per_carat":
                # One service line per gem line: price_unit = base_price × weight_ct
                for gem_line in lines:
                    size_label = gem_line.standard_size_id.label or f"{gem_line.weight_ct:g} ct"
                    cut = dict(GEM_CUT_SHAPES).get(gem_line.cut_shape, gem_line.cut_shape or "")
                    stone_desc = f"{gem_line.quantity} × {gem_line.gem_type_id.name}"
                    if cut:
                        stone_desc += f" {cut}"
                    if size_label:
                        stone_desc += f" {size_label}"
                    ServiceLine.create({
                        "order_id": self.id,
                        "product_id": product.id,
                        "name": stone_desc,
                        "quantity": gem_line.quantity * self.quantity,
                        "price_unit": base_price * gem_line.weight_ct,
                        "operation_id": operation_id,
                    })
            else:
                # Fixed price: group all lines, one service line per rule
                total_qty = sum(l.quantity for l in lines) * self.quantity
                stone_parts = []
                for line in lines:
                    size_label = line.standard_size_id.label or f"{line.weight_ct:g} ct"
                    cut = dict(GEM_CUT_SHAPES).get(line.cut_shape, line.cut_shape or "")
                    stone_desc = f"{line.quantity} × {line.gem_type_id.name}"
                    if cut:
                        stone_desc += f" {cut}"
                    if size_label:
                        stone_desc += f" {size_label}"
                    stone_parts.append(stone_desc)
                ServiceLine.create({
                    "order_id": self.id,
                    "product_id": product.id,
                    "name": ", ".join(stone_parts),
                    "quantity": total_qty,
                    "price_unit": base_price,
                    "operation_id": operation_id,
                })

    def action_generate_operations(self):
        order_operation_model = self.env["jewelry.repair.order.operation"]
        for order in self:
            saved_weight_before = {
                op.operation_id.id: op.weight_before
                for op in order.order_operation_ids
                if op.weight_before
            }
            order.order_operation_ids.unlink()
            grouped_services = {}
            for line in order.service_line_ids.sorted(lambda line: (line.operation_id.sequence, line.sequence, line.id)):
                if not line.operation_id:
                    continue
                grouped_services.setdefault(line.operation_id.id, []).append(line)

            for operation_id, lines in grouped_services.items():
                operation = lines[0].operation_id
                new_op = order_operation_model.create(
                    {
                        "order_id": order.id,
                        "operation_id": operation.id,
                        "sequence": operation.sequence,
                        "service_line_ids": [(6, 0, [line.id for line in lines])],
                    }
                )
                if operation.id in saved_weight_before:
                    new_op.weight_before = saved_weight_before[operation.id]
            order._sync_operation_flow()

    def action_auto_assign_operations(self):
        executor_model = self.env["jewelry.repair.executor"]
        for order in self:
            for operation in order.order_operation_ids.filtered(
                lambda op: not op.assigned_user_id and op.state != "cancel"
            ):
                executor = (
                    operation.executor_id
                    or operation.operation_id.default_executor_id
                    or executor_model._find_for_user(operation.operation_id.default_user_id)
                )
                if executor:
                    operation.executor_id = executor
                    operation.assigned_user_id = executor.user_id

    def _check_weight_field(self, weight_value, field_label):
        """Check a weight field.
        Returns warning message string for privileged users, raises UserError for others.
        Returns None if field is filled.
        """
        if weight_value:
            return None
        msg = _("%s is not filled in. Please weigh the item and enter the value before proceeding.") % field_label
        if self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_manage_any_operation"):
            return msg
        raise UserError(msg)

    def _metal_balance(self):
        """Return (weight_in, weight_out, loss, loss_percent) for the order's metal.

        Same formula as the jewelry.order.client.loss report: workshop metal put
        into the item counts as input, metal returned to storage counts as output.
        Invoiced material is sold to the client, so it stays out of the balance.
        """
        self.ensure_one()
        added = 0.0
        returned = 0.0
        for line in self.material_line_ids:
            weight = line.weight or 0.0
            if not weight:
                continue
            if line.return_to_storage:
                returned += weight
            elif line.consume_from_stock and not line.include_in_invoice:
                added += weight
        weight_in = (self.received_weight or 0.0) + added
        weight_out = (self.metal_delivered_weight or 0.0) + returned
        loss = weight_in - weight_out
        loss_percent = (loss / weight_in * 100.0) if weight_in else 0.0
        return weight_in, weight_out, loss, loss_percent

    def _check_weight_discrepancy(self):
        """Return a warning string if the metal balance differs beyond the allowed
        threshold (10% for new manufacturing, 5% for repair).
        Returns None if within tolerance or not computable."""
        self.ensure_one()
        weight_in, weight_out, _loss, loss_percent = self._metal_balance()
        if weight_in <= 0 or weight_out <= 0:
            return None
        diff_percent = abs(loss_percent)
        threshold = 10.0 if self.new_product_manufacturing else 5.0
        if diff_percent <= threshold:
            return None
        return _(
            "Metal balance differs by %(diff).1f%% — in %(in).3f g "
            "(received + workshop metal) vs out %(out).3f g "
            "(delivered metal + returned), exceeding the %(limit).0f%% limit."
        ) % {"diff": diff_percent, "in": weight_in, "out": weight_out, "limit": threshold}

    @staticmethod
    def _weight_warning_notification(message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Warning"),
                "message": message,
                "type": "warning",
                "sticky": True,
            },
        }

    def action_start(self):
        for order in self:
            if order.state in ("cancel", "delivered"):
                continue
            warning = None if order.new_product_manufacturing else order._check_weight_field(order.received_weight, _("Received Weight"))
            if not order.order_operation_ids:
                order.action_generate_operations()
            if not order.order_operation_ids:
                raise UserError(
                    _("No repair operations were generated. Add services with linked operations before starting the order.")
                )
            order.state = "in_progress"
            order._sync_operation_flow(force_activate=True)
            if order.received_weight:
                first_op = order.order_operation_ids.sorted(
                    lambda op: (op.sequence, op.id)
                )[:1]
                if first_op and not first_op.weight_before:
                    first_op.weight_before = order.received_weight
        if warning:
            return self._weight_warning_notification(warning)

    def action_mark_ready(self):
        self.ensure_one()
        pending_ops = self.order_operation_ids.filtered(
            lambda o: o.state not in ("done", "cancel")
        )
        if pending_ops:
            is_manager = self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_manager")
            if not is_manager:
                raise UserError(_("All order operations must be completed before marking the order as ready."))
            wizard = self.env["jewelry.repair.force.ready.wizard"].create({
                "order_id": self.id,
                "pending_count": len(pending_ops),
            })
            return {
                "type": "ir.actions.act_window",
                "res_model": "jewelry.repair.force.ready.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
                "name": _("Uncompleted Operations"),
            }
        self.write({"state": "ready"})
        self._compute_area_losses()

    def _get_weight_tracking_mode(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "jewelry_repair_base.weight_tracking_mode", "all"
        )

    def _weight_tracking_applies(self):
        """Return True if weight tracking is active for this specific order."""
        self.ensure_one()
        mode = self._get_weight_tracking_mode()
        if mode == "disabled":
            return False
        if mode == "new_product_only":
            return self.new_product_manufacturing
        return True

    def _compute_weight_tracking_enabled(self):
        mode = self._get_weight_tracking_mode()
        for order in self:
            if mode == "disabled":
                order.weight_tracking_enabled = False
            elif mode == "new_product_only":
                order.weight_tracking_enabled = order.new_product_manufacturing
            else:
                order.weight_tracking_enabled = True

    @api.depends("area_loss_ids.weight_in", "area_loss_ids.loss")
    def _compute_total_metal_loss_percent(self):
        for order in self:
            total_in = sum(order.area_loss_ids.mapped("weight_in"))
            total_loss = sum(order.area_loss_ids.mapped("loss"))
            order.total_metal_loss_percent = (total_loss / total_in * 100.0) if total_in else 0.0

    def _compute_area_losses(self):
        """Calculate weight_in / weight_out per work area and store in area_loss_ids.
        Called automatically when order transitions to 'ready'.

        Added-weight adjustment (gems + materials):
        All weights entered by masters (weight_before) include any material/gems
        that were physically added to the item in prior operations.
        To isolate pure metal loss we subtract these additions from raw weights.

        Gems: all added during the gem setting area (identified by is_gem_setting flag on ops).
              weight_out of gem area and all subsequent areas are reduced by gem_weight_total_g.

        Materials (consume_from_stock=True, weight > 0, linked to an operation):
          Materials are additions to the item. Cumulative material weight is subtracted from
          weight_out of the area where added and weight_in of all subsequent areas.

        The casting area is computed like any other area: weight_before of its operation
        against weight_before of the next one. It used to take weight_in from the materials
        consumed there instead, which threw away the weight the master had entered.
        """
        AreaLoss = self.env["jewelry.order.area.loss"]
        mode = self._get_weight_tracking_mode()
        for order in self:
            is_new_mfg = order.new_product_manufacturing
            tracking_applies = (
                mode == "all"
                or (mode == "new_product_only" and is_new_mfg)
            )
            if not tracking_applies:
                order.area_loss_ids.unlink()
                continue
            ops = order.order_operation_ids.filtered(
                lambda op: op.state == "done"
                and op.operation_id.area_id
                and op.weight_before > 0
            ).sorted(lambda op: (
                op.operation_id.area_id.sequence,
                op.operation_id.area_id.id,
                op.sequence,
                op.id,
            ))

            if not ops:
                order.area_loss_ids.unlink()
                continue

            # Group by area preserving area sequence order
            area_ops = {}
            area_order = []
            for op in ops:
                area = op.operation_id.area_id
                if area.id not in area_ops:
                    area_ops[area.id] = []
                    area_order.append(area)
                area_ops[area.id].append(op)

            gem_weight = order.gem_weight_total_g or 0.0

            # Find index of the gem setting area (area containing is_gem_setting ops)
            gem_area_idx = -1
            for i, area in enumerate(area_order):
                if any(op.operation_id.is_gem_setting for op in area_ops[area.id]):
                    gem_area_idx = i
                    break

            # Build per-area material weight.
            # op_area_idx maps operation id → index in area_order
            op_area_idx = {}
            for i, area in enumerate(area_order):
                for op in area_ops[area.id]:
                    op_area_idx[op.id] = i

            material_weight_by_area = [0.0] * len(area_order)
            return_weight_by_area = [0.0] * len(area_order)
            for mat in order.material_line_ids:
                if not mat.weight or not mat.order_operation_id:
                    continue
                idx = op_area_idx.get(mat.order_operation_id.id)
                if idx is None:
                    continue
                if mat.return_to_storage:
                    return_weight_by_area[idx] += mat.weight
                elif mat.consume_from_stock:
                    material_weight_by_area[idx] += mat.weight

            # cumulative_material[i] = total addition-material weight in areas 0..i (inclusive)
            cumulative_material = [0.0] * len(area_order)
            running = 0.0
            for i in range(len(area_order)):
                running += material_weight_by_area[i]
                cumulative_material[i] = running

            # cumulative_return[i] = total returned-to-storage weight in areas 0..i (inclusive)
            cumulative_return = [0.0] * len(area_order)
            running = 0.0
            for i in range(len(area_order)):
                running += return_weight_by_area[i]
                cumulative_return[i] = running

            rows = []
            for i, area in enumerate(area_order):
                raw_in = area_ops[area.id][0].weight_before
                gem_adj_in = gem_weight if gem_area_idx >= 0 and i > gem_area_idx else 0.0
                mat_adj_in = cumulative_material[i - 1] if i > 0 else 0.0
                ret_adj_in = cumulative_return[i - 1] if i > 0 else 0.0
                weight_in = raw_in - gem_adj_in - mat_adj_in + ret_adj_in

                if i + 1 < len(area_order):
                    next_area = area_order[i + 1]
                    raw_out = area_ops[next_area.id][0].weight_before
                else:
                    raw_out = order.delivered_weight or 0.0

                gem_adj_out = gem_weight if gem_area_idx >= 0 and i >= gem_area_idx else 0.0
                mat_adj_out = cumulative_material[i]
                ret_adj_out = cumulative_return[i]
                weight_out = raw_out - gem_adj_out - mat_adj_out + ret_adj_out

                rows.append({
                    "order_id": order.id,
                    "area_id": area.id,
                    "weight_in": weight_in,
                    "weight_out": weight_out,
                })

            order.area_loss_ids.unlink()
            AreaLoss.create(rows)

    def _metal_cleanup_documents(self):
        """Hook: remove metal documents tied to these orders on cancel/reset.

        No-op in base; jewelry_metal_accounting fills it in.
        """
        return

    def _collect_pre_acceptance_warnings(self):
        """Hook: per-order pre-acceptance sync + warnings (e.g. metal documents).

        Returns a list of warning strings. No-op in base.
        """
        self.ensure_one()
        return []

    def action_cancel(self):
        self._metal_cleanup_documents()
        self.area_loss_ids.unlink()
        self.write({"state": "cancel"})

    def action_reset_to_draft(self):
        self._metal_cleanup_documents()
        self.area_loss_ids.unlink()
        self.write({"state": "draft"})
        self.order_operation_ids.filtered(lambda operation: operation.state in ("ready", "accepted", "in_progress")).write(
            {"state": "pending", "started_at": False, "accepted_at": False, "accepted_by_user_id": False}
        )
        for order in self:
            order.ready_accepted_by_manager = False
            order.ready_accepted_at = False
            order._set_current_holder(order.create_uid, "reception")

    def _sync_operation_flow(self, force_activate=False):
        for order in self:
            operations = order.order_operation_ids.sorted(lambda op: (op.sequence, op.id))
            active_operations = operations.filtered(lambda op: op.state != "cancel")
            first_open = active_operations.filtered(lambda op: op.state != "done")[:1]

            for operation in active_operations:
                if first_open and operation == first_open:
                    if operation.state == "pending" and (force_activate or order.state == "in_progress"):
                        operation.state = "ready"
                elif operation.state == "ready":
                    operation.state = "pending"

            if order.state in ("delivered", "cancel"):
                continue

            if active_operations and all(operation.state == "done" for operation in active_operations):
                order.state = "ready"
                order._compute_area_losses()
            elif any(operation.state in ("ready", "in_progress", "done") for operation in active_operations):
                order.state = "in_progress"
            elif order.state != "draft":
                order.state = "draft"

    def action_accept_ready_item(self):
        manager_group = "jewelry_repair_base.group_jewelry_repair_manager"
        if not self.env.context.get("weight_discrepancy_confirmed"):
            for order in self:
                msg = order._check_weight_discrepancy()
                if msg:
                    wizard = self.env["jewelry.repair.weight.discrepancy.wizard"].create({
                        "order_id": order.id,
                        "message": msg,
                    })
                    return {
                        "type": "ir.actions.act_window",
                        "res_model": "jewelry.repair.weight.discrepancy.wizard",
                        "res_id": wizard.id,
                        "view_mode": "form",
                        "target": "new",
                        "name": _("Weight Discrepancy"),
                    }
        warnings = []
        for order in self:
            if not (self.env.user.has_group(manager_group) or self.env.user.has_group("base.group_system")):
                raise UserError(_("Only a manager can accept a ready item from production."))
            if order.state != "ready":
                raise UserError(_("Only ready orders can be accepted by the manager."))
            if any(operation.state != "done" for operation in order.order_operation_ids):
                raise UserError(_("All operations must be completed before manager acceptance."))
            warnings += order._collect_pre_acceptance_warnings()
            weight_warning = order._check_weight_field(order.delivered_weight, _("Delivered Weight"))
            if weight_warning:
                warnings.append(weight_warning)
            order.write(
                {
                    "ready_accepted_by_manager": True,
                    "ready_accepted_at": fields.Datetime.now(),
                }
            )
            order._set_current_holder(self.env.user, "ready_for_delivery")
        if warnings:
            return self._weight_warning_notification("\n".join(warnings))

    def action_open_cert_parse_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.gem.cert.parse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_open_service_products(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Repair Service Products"),
            "res_model": "product.template",
            "view_mode": "tree,form",
            "domain": [("repair_service_ok", "=", True)],
            "context": {"default_repair_service_ok": True},
        }

    def action_open_apply_metal_rate_wizard(self):
        self.ensure_one()
        self._check_editable()
        if not self.material_line_ids:
            raise UserError(_("There are no material lines to update."))
        if not self.metal_rate_at:
            raise UserError(_("Set the order metal rate datetime before applying it to materials."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Apply Metal Rate Datetime"),
            "res_model": "jewelry.repair.apply.metal.rate.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_material_line_count": len(self.material_line_ids),
            },
        }

    def action_apply_metal_rate_to_materials(self):
        self._check_editable()
        for order in self:
            if not order.metal_rate_at:
                raise UserError(_("Set the order metal rate datetime before applying it to materials."))
            order.material_line_ids.write({"rate_datetime": order.metal_rate_at})

    def action_open_operation_catalog(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Operations"),
            "res_model": "jewelry.repair.operation",
            "view_mode": "tree,form",
        }

    def action_open_order_operations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Order Operations"),
            "res_model": "jewelry.repair.order.operation",
            "view_mode": "kanban,tree,form",
            "domain": [("order_id", "=", self.id)],
            "context": {"default_order_id": self.id},
        }

    def action_open_item_image(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/image?model=jewelry.repair.order&id={self.id}&field=item_image",
            "target": "new",
        }

    def action_print_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_base.report_jewelry_repair_order_invoice_document/%s" % self.id,
            "target": "new",
        }

    def action_print_order_card(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_base.report_jewelry_repair_order_card_document/%s" % self.id,
            "target": "new",
        }
