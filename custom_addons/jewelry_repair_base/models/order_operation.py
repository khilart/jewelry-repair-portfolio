from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairOrderOperation(models.Model):
    _name = "jewelry.repair.order.operation"
    _description = "Jewelry Repair Order Operation"
    _order = "board_priority, sequence, planned_date, id"

    order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        required=True,
        ondelete="cascade",
    )
    order_item_image = fields.Image(
        related="order_id.item_image",
        string="Item Photo",
        readonly=True,
    )
    operation_id = fields.Many2one(
        "jewelry.repair.operation",
        string="Operation",
        required=True,
        group_expand="_group_expand_operation_id",
    )
    executor_id = fields.Many2one(
        "jewelry.repair.executor",
        string="Planned Executor",
        group_expand="_group_expand_executor_id",
    )
    name = fields.Char(related="operation_id.name", readonly=True)
    sequence = fields.Integer(default=10, required=True)
    assigned_user_id = fields.Many2one(
        "res.users",
        string="Assigned To",
        group_expand="_group_expand_assigned_user_id",
    )
    estimated_duration_minutes = fields.Float(
        string="Estimated Duration (Minutes)",
        compute="_compute_estimated_duration",
        store=True,
    )
    estimated_duration_days = fields.Float(string="Estimated Duration (Days)")
    estimated_duration_display = fields.Char(
        string="Estimated Work Time",
        compute="_compute_estimated_duration",
        store=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("ready", "Ready"),
            ("accepted", "Accepted"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="pending",
        required=True,
    )
    order_state = fields.Selection(related="order_id.state", string="Order Status", readonly=True)
    planned_date = fields.Date(string="Planned Date")
    planned_scope = fields.Selection(
        [
            ("overdue", "Overdue"),
            ("today", "Today"),
            ("tomorrow", "Tomorrow"),
            ("future", "Future"),
            ("no_date", "No Planned Date"),
        ],
        string="Planning",
        compute="_compute_planned_scope",
        store=True,
    )
    board_priority = fields.Integer(
        string="Board Priority",
        compute="_compute_board_priority",
        store=True,
        readonly=True,
    )
    accepted_by_user_id = fields.Many2one("res.users", string="Accepted By", readonly=True, copy=False)
    accepted_at = fields.Datetime(string="Accepted At", readonly=True, copy=False)
    started_at = fields.Datetime(string="Started At")
    done_at = fields.Datetime(string="Done At")
    metal_was_added = fields.Boolean(
        string="Metal Was Added",
        default=False,
        help="Check if metal was added during this operation (soldering, resizing). Used for metal consumption calculation.",
    )
    notes = fields.Text(string="Execution Notes")
    next_order_operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        string="Next Operation",
        compute="_compute_next_operation_data",
    )
    order_deadline_date = fields.Datetime(
        related="order_id.deadline_date",
        string="Order Deadline",
        readonly=True,
    )
    order_partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
        readonly=True,
    )
    order_deadline_display = fields.Char(
        string="Deadline",
        compute="_compute_order_deadline_display",
    )
    order_description = fields.Text(
        related="order_id.description",
        string="Order Notes",
        readonly=True,
    )
    order_item_type_id = fields.Many2one(
        related="order_id.item_type_id",
        string="Item Type",
        readonly=True,
    )
    order_item_size_id = fields.Many2one(
        related="order_id.item_size_id",
        string="Item Size",
        readonly=True,
    )
    order_alloy_id = fields.Many2one(
        related="order_id.alloy_id",
        string="Alloy",
        readonly=True,
    )
    order_quantity = fields.Integer(
        related="order_id.quantity",
        string="Quantity",
        readonly=True,
    )
    order_received_weight = fields.Float(
        related="order_id.received_weight",
        string="Received Weight (g)",
        readonly=True,
        digits=(16, 3),
    )
    weight_before = fields.Float(string="Weight Before (g)", digits=(16, 3))
    is_overdue = fields.Boolean(
        string="Overdue",
        compute="_compute_is_overdue",
    )
    next_executor_id = fields.Many2one(
        "jewelry.repair.executor",
        string="Next Planned Executor",
        compute="_compute_next_operation_data",
        readonly=True,
    )
    next_assigned_user_id = fields.Many2one(
        "res.users",
        string="Next Assignee",
        compute="_compute_next_operation_data",
        readonly=True,
    )
    prev_order_operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        string="Previous Operation",
        compute="_compute_prev_operation_data",
    )
    prev_executor_id = fields.Many2one(
        "jewelry.repair.executor",
        string="Previous Planned Executor",
        compute="_compute_prev_operation_data",
        readonly=True,
    )
    prev_assigned_user_id = fields.Many2one(
        "res.users",
        string="Previous Assignee",
        compute="_compute_prev_operation_data",
        readonly=True,
    )
    service_line_ids = fields.Many2many(
        "jewelry.repair.service.line",
        "jewelry_repair_order_operation_service_line_rel",
        "order_operation_id",
        "service_line_id",
        string="Source Services",
    )
    material_line_ids = fields.One2many(
        "jewelry.repair.material.line",
        "order_operation_id",
        string="Materials",
    )

    @api.model_create_multi
    def create(self, vals_list):
        executor_model = self.env["jewelry.repair.executor"]
        for vals in vals_list:
            if vals.get("executor_id") and not vals.get("assigned_user_id"):
                executor = executor_model.browse(vals["executor_id"])
                if executor.user_id:
                    vals["assigned_user_id"] = executor.user_id.id
            elif not vals.get("executor_id") and vals.get("assigned_user_id"):
                executor = executor_model._find_for_user(self.env["res.users"].browse(vals["assigned_user_id"]))
                if executor:
                    vals["executor_id"] = executor.id
        return super().create(vals_list)

    def write(self, vals):
        executor_model = self.env["jewelry.repair.executor"]
        if vals.get("executor_id") and not vals.get("assigned_user_id"):
            executor = executor_model.browse(vals["executor_id"])
            if executor.user_id:
                vals = dict(vals, assigned_user_id=executor.user_id.id)
        elif vals.get("assigned_user_id") and not vals.get("executor_id"):
            executor = executor_model._find_for_user(
                self.env["res.users"].browse(vals["assigned_user_id"])
            )
            if executor:
                vals = dict(vals, executor_id=executor.id)
        return super().write(vals)

    @api.depends("service_line_ids.quantity", "service_line_ids.operation_id.duration_minutes")
    def _compute_estimated_duration(self):
        for operation in self:
            total_minutes = sum(
                line.quantity * line.operation_id.duration_minutes
                for line in operation.service_line_ids
                if line.operation_id and line.quantity
            )
            operation.estimated_duration_minutes = total_minutes
            operation.estimated_duration_days = total_minutes / (8.0 * 60.0)

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
            operation.estimated_duration_display = " ".join(parts)

    @api.depends("order_deadline_date")
    def _compute_order_deadline_display(self):
        for operation in self:
            if operation.order_deadline_date:
                dt = fields.Datetime.context_timestamp(operation, operation.order_deadline_date)
                operation.order_deadline_display = dt.strftime("%d.%m.%Y %H:%M")
            else:
                operation.order_deadline_display = ""

    @api.depends("order_deadline_date", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for operation in self:
            operation.is_overdue = (
                operation.order_deadline_date
                and operation.order_deadline_date < now
                and operation.state not in ("done", "cancel")
            )

    @api.depends("planned_date", "state")
    def _compute_planned_scope(self):
        today = fields.Date.context_today(self)
        tomorrow = today + timedelta(days=1)
        for operation in self:
            if not operation.planned_date:
                operation.planned_scope = "no_date"
            elif operation.planned_date < today and operation.state not in ("done", "cancel"):
                operation.planned_scope = "overdue"
            elif operation.planned_date == today:
                operation.planned_scope = "today"
            elif operation.planned_date == tomorrow:
                operation.planned_scope = "tomorrow"
            else:
                operation.planned_scope = "future"

    @api.depends("state")
    def _compute_board_priority(self):
        priority_map = {
            "in_progress": 10,
            "ready": 20,
            "accepted": 30,
            "pending": 90,
            "done": 100,
            "cancel": 110,
        }
        for operation in self:
            operation.board_priority = priority_map.get(operation.state, 999)

    @api.depends(
        "order_id.order_operation_ids.sequence",
        "order_id.order_operation_ids.state",
        "order_id.order_operation_ids.executor_id",
        "order_id.order_operation_ids.assigned_user_id",
    )
    def _compute_next_operation_data(self):
        for operation in self:
            sorted_ops = operation.order_id.order_operation_ids.filtered(
                lambda candidate: candidate.state != "cancel"
            ).sorted(lambda candidate: (candidate.sequence, candidate.id))
            found = False
            for candidate in sorted_ops:
                if (candidate.sequence, candidate.id) > (operation.sequence, operation.id):
                    operation.next_order_operation_id = candidate.id
                    operation.next_executor_id = candidate.executor_id
                    operation.next_assigned_user_id = candidate.assigned_user_id
                    found = True
                    break
            if not found:
                operation.next_order_operation_id = False
                operation.next_executor_id = False
                operation.next_assigned_user_id = False

    @api.depends(
        "order_id.order_operation_ids.sequence",
        "order_id.order_operation_ids.state",
        "order_id.order_operation_ids.executor_id",
        "order_id.order_operation_ids.assigned_user_id",
    )
    def _compute_prev_operation_data(self):
        for operation in self:
            sorted_ops = operation.order_id.order_operation_ids.filtered(
                lambda candidate: candidate.state != "cancel"
            ).sorted(lambda candidate: (candidate.sequence, candidate.id))
            prev = None
            for candidate in sorted_ops:
                if (candidate.sequence, candidate.id) >= (operation.sequence, operation.id):
                    break
                prev = candidate
            if prev:
                operation.prev_order_operation_id = prev.id
                operation.prev_executor_id = prev.executor_id
                operation.prev_assigned_user_id = prev.assigned_user_id
            else:
                operation.prev_order_operation_id = False
                operation.prev_executor_id = False
                operation.prev_assigned_user_id = False

    @api.model
    def _group_expand_assigned_user_id(self, users, domain, order):
        assigned_users = self.search(domain).mapped("assigned_user_id").filtered(lambda user: not user.share)
        if domain:
            return (users | assigned_users).sorted(lambda user: user.name or "")

        master_group = self.env.ref("jewelry_repair_base.group_jewelry_repair_master")
        master_users = self.env["res.users"].search(
            [("groups_id", "in", [master_group.id]), ("share", "=", False)],
            order=order or "name",
        )
        return (users | master_users | assigned_users).sorted(lambda user: user.name or "")

    @api.model
    def _group_expand_operation_id(self, operations, domain, order):
        active_operations = self.search(domain).mapped("operation_id")
        return (operations | active_operations).sorted(
            lambda op: (op.sequence, op.name or "", op.id)
        )

    @api.model
    def _group_expand_executor_id(self, executors, domain, order):
        executor_model = self.env["jewelry.repair.executor"]
        assigned_executors = self.search(domain).mapped("executor_id")
        if self.env.context.get("planning_board"):
            planned_executors = executor_model.search([("active", "=", True)], order=order or "sequence, name, id")
            return (executors | planned_executors | assigned_executors).sorted(
                lambda executor: (executor.sequence, executor.name or "", executor.id)
            )
        if domain:
            return (executors | assigned_executors).sorted(
                lambda executor: (executor.sequence, executor.name or "", executor.id)
            )

        planned_executors = executor_model.search([("active", "=", True)], order=order or "sequence, name, id")
        return (executors | planned_executors | assigned_executors).sorted(
            lambda executor: (executor.sequence, executor.name or "", executor.id)
        )

    def action_set_ready(self):
        for operation in self:
            if operation.state == "pending":
                operation.state = "ready"
                operation.order_id.state = "in_progress"

    def action_open_item_image(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/image?model=jewelry.repair.order&id={self.order_id.id}&field=item_image",
            "target": "new",
        }

    def action_reassign_next(self):
        self.ensure_one()
        next_op = self.next_order_operation_id
        if not next_op:
            return
        wizard = self.env["jewelry.repair.reassign.next.wizard"].create({
            "operation_id": self.id,
            "new_executor_id": next_op.executor_id.id or False,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Reassign Next Operation"),
            "res_model": "jewelry.repair.reassign.next.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_reassign_self(self):
        self.ensure_one()
        wizard = self.env["jewelry.repair.reassign.next.wizard"].create({
            "operation_id": self.id,
            "reassign_self": True,
            "new_executor_id": self.executor_id.id or False,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Reassign Operation"),
            "res_model": "jewelry.repair.reassign.next.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_kanban_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Work Operation"),
            "res_model": "jewelry.repair.order.operation",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref("jewelry_repair_base.view_jewelry_repair_order_operation_form_kanban").id,
            "target": "current",
            "context": dict(self.env.context),
        }

    @api.model
    def action_open_completed_operations_menu(self):
        domain = [
            ("state", "=", "done"),
            ("order_id.state", "!=", "cancel"),
        ]
        if not (
            self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_manager")
            or self.env.user.has_group("base.group_system")
        ):
            domain.append(("assigned_user_id", "=", self.env.user.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Completed Operations"),
            "res_model": "jewelry.repair.order.operation",
            "view_mode": "kanban,tree,form",
            "search_view_id": self.env.ref("jewelry_repair_base.view_jewelry_repair_order_operation_search").id,
            "domain": domain,
            "context": {"group_by": "executor_id", "completed_board": True},
        }

    def _can_manage_any_operation(self):
        return self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_manage_any_operation") or self.env.user.has_group("base.group_system")

    def _check_assignee_access(self):
        if self._can_manage_any_operation():
            return
        for operation in self:
            if operation.assigned_user_id and operation.assigned_user_id != self.env.user:
                raise UserError(_("Only the assigned user can perform this action."))

    def action_assign_to_me(self):
        executor = self.env["jewelry.repair.executor"]._find_for_user(self.env.user)
        values = {"assigned_user_id": self.env.user.id}
        if executor:
            values["executor_id"] = executor.id
        self.write(values)

    def _accept_item_inline(self):
        """Accept item without wizard (used when weight tracking is off or manager enters weight)."""
        self._check_assignee_access()
        executor = self.executor_id or self.env["jewelry.repair.executor"]._find_for_user(
            self.assigned_user_id or self.env.user
        )
        self.write({
            "state": "accepted",
            "accepted_by_user_id": self.env.user.id,
            "accepted_at": fields.Datetime.now(),
            "assigned_user_id": self.assigned_user_id.id or self.env.user.id,
            "executor_id": executor.id if executor else False,
        })
        self.order_id._set_current_holder(self.env.user, "in_work")

    def action_accept_item(self):
        self.ensure_one()
        if self.state != "ready":
            raise UserError(_("Only ready operations can be accepted."))
        if not self.order_id._weight_tracking_applies():
            self._accept_item_inline()
            return False
        entry_by = self.env["ir.config_parameter"].sudo().get_param(
            "jewelry_repair_base.weight_entry_by", "master"
        )
        if entry_by == "manager":
            self._accept_item_inline()
            return False
        wizard = self.env["jewelry.accept.item.wizard"].create({
            "operation_id": self.id,
            "weight_before": self.order_id.received_weight or 0.0,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Accept Item"),
            "res_model": "jewelry.accept.item.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_start(self):
        self._check_assignee_access()
        for operation in self:
            if operation.state not in ("accepted", "in_progress"):
                raise UserError(_("Only accepted operations can be started."))
            values = {"state": "in_progress"}
            if not operation.started_at:
                values["started_at"] = fields.Datetime.now()
            operation.write(values)
            if operation.order_id.state == "draft":
                operation.order_id.state = "in_progress"

    def action_mark_done(self):
        self._check_assignee_access()
        for operation in self:
            if operation.state not in ("accepted", "in_progress"):
                raise UserError(_("Only accepted or in-progress operations can be completed."))
            values = {
                "state": "done",
                "done_at": fields.Datetime.now(),
            }
            if not operation.started_at:
                values["started_at"] = fields.Datetime.now()
            operation.write(values)
            operation.order_id._sync_operation_flow()
            next_op = operation.next_order_operation_id
            if (
                next_op
                and next_op.state == "ready"
                and next_op.assigned_user_id == self.env.user
            ):
                next_op.write({
                    "state": "accepted",
                    "accepted_by_user_id": self.env.user.id,
                    "accepted_at": fields.Datetime.now(),
                })
                next_op.order_id._set_current_holder(self.env.user, "in_work")

        return {"type": "ir.actions.client", "tag": "reload"}

    def action_return_to_rework(self):
        self._check_assignee_access()
        for operation in self:
            if operation.state != "done":
                raise UserError(_("Only completed operations can be returned to rework."))
            if operation.order_id.state == "delivered":
                raise UserError(_("Delivered orders cannot be returned to rework."))

            values = {
                "state": "ready" if operation.assigned_user_id else "pending",
                "accepted_by_user_id": False,
                "accepted_at": False,
                "started_at": False,
                "done_at": False,
            }
            operation.write(values)

            order = operation.order_id
            order.write(
                {
                    "state": "in_progress",
                    "ready_accepted_by_manager": False,
                    "ready_accepted_at": False,
                }
            )
            if operation.assigned_user_id:
                order._set_current_holder(operation.assigned_user_id, "in_work")
            order._sync_operation_flow(force_activate=True)

    def action_reset_to_pending(self):
        for operation in self:
            operation.write(
                {
                    "state": "pending",
                    "accepted_by_user_id": False,
                    "accepted_at": False,
                    "started_at": False,
                    "done_at": False,
                }
            )
            operation.order_id._sync_operation_flow()

    def action_cancel(self):
        self.write({"state": "cancel"})
        self.mapped("order_id")._sync_operation_flow()
