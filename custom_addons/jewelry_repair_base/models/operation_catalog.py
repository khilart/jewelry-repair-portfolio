from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairExecutor(models.Model):
    _name = "jewelry.repair.executor"
    _description = "Jewelry Repair Executor"
    _order = "sequence, name, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(string="Planning Sequence", default=10, required=True)
    user_id = fields.Many2one("res.users", string="Linked User", required=True)
    manager_user_ids = fields.Many2many(
        "res.users",
        "jewelry_repair_executor_manager_rel",
        "executor_id",
        "user_id",
        string="Planning Managers",
        help="Reserved for future planning restrictions by manager or workshop lead.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("executor_user_unique", "unique(user_id)", "Each user can only be linked to one operation executor."),
    ]

    @api.model
    def _find_for_user(self, user):
        if not user:
            return self.browse()
        return self.with_context(active_test=False).search([("user_id", "=", user.id)], limit=1)

    @api.model
    def _sync_existing_executors(self):
        users = (
            self.env["jewelry.repair.operation"].search([]).mapped("default_user_id")
            | self.env["jewelry.repair.order.operation"].search([]).mapped("assigned_user_id")
        ).filtered(lambda user: user and not user.share)

        for user in users:
            self.with_context(active_test=False).search(
                [("user_id", "=", user.id)],
                limit=1,
            ) or self.create(
                {
                    "name": user.name,
                    "user_id": user.id,
                }
            )

        for operation in self.env["jewelry.repair.operation"].search(
            [("default_executor_id", "=", False), ("default_user_id", "!=", False)]
        ):
            executor = self._find_for_user(operation.default_user_id)
            if executor:
                operation.default_executor_id = executor

        for order_operation in self.env["jewelry.repair.order.operation"].search(
            [("executor_id", "=", False), ("assigned_user_id", "!=", False)]
        ):
            executor = self._find_for_user(order_operation.assigned_user_id)
            if executor:
                order_operation.executor_id = executor

    def _register_hook(self):
        result = super()._register_hook()
        self._sync_existing_executors()
        return result


class JewelryWorkArea(models.Model):
    _name = "jewelry.work.area"
    _description = "Work Area"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10, required=True)
    is_casting = fields.Boolean(
        string="Casting Area",
        help="Weight input for this area is taken from consumed materials, not weight_before. "
             "Used for new product manufacturing where the item does not exist before casting.",
    )


class JewelryRepairOperation(models.Model):
    _name = "jewelry.repair.operation"
    _description = "Jewelry Repair Operation"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    area_id = fields.Many2one(
        "jewelry.work.area",
        string="Work Area",
        ondelete="set null",
    )
    is_gem_setting = fields.Boolean(
        string="Gem Setting Operation",
        help="Operations of this type are grouped as a gem setting block in metal loss reports. "
             "Gem weight is subtracted from all subsequent operation weights.",
    )

    @api.model
    def name_create(self, name):
        if self.search([("name", "=ilike", name.strip())], limit=1):
            raise UserError(
                _("An operation named \"%s\" already exists. To create a duplicate, use \"Create and edit...\"") % name
            )
        return super().name_create(name)
    sequence = fields.Integer(default=10, required=True)
    duration_value = fields.Float(
        string="Estimated Duration",
        default=0.0,
        help="Informational minimum duration used to estimate the earliest possible completion date.",
    )
    duration_unit = fields.Selection(
        [
            ("minutes", "Minutes"),
            ("hours", "Hours"),
            ("days", "Days"),
        ],
        string="Duration Unit",
        default="days",
        required=True,
    )
    duration_days = fields.Float(
        string="Estimated Duration (Days)",
        compute="_compute_duration_metrics",
        store=True,
        help="Technical normalized value used for date estimation.",
    )
    duration_minutes = fields.Float(
        string="Estimated Duration (Minutes)",
        compute="_compute_duration_metrics",
        store=True,
        help="Technical normalized value in working minutes used for date estimation.",
    )
    default_executor_id = fields.Many2one("jewelry.repair.executor", string="Default Executor")
    default_user_id = fields.Many2one("res.users", string="Default Assignee")
    active = fields.Boolean(default=True)
    loss_recoverable_percent = fields.Float(
        string="Recoverable Loss %",
        default=0.0,
        help="Percentage of recoverable metal losses (filings, chips) relative to the received item weight.",
    )
    loss_irrecoverable_percent = fields.Float(
        string="Irrecoverable Loss %",
        default=0.0,
        help="Percentage of irrecoverable metal losses (dust, burnout) relative to the received item weight.",
    )
    is_gem_setting = fields.Boolean(
        string="Gem Setting Operation",
        default=False,
        help="Mark this operation as gem setting. Setting losses will be distributed proportionally "
             "between executors of these operations based on service line quantities.",
    )

    @api.depends("duration_value", "duration_unit")
    def _compute_duration_metrics(self):
        minute_map = {
            "minutes": 1.0,
            "hours": 60.0,
            "days": 8.0 * 60.0,
        }
        for operation in self:
            operation.duration_minutes = operation.duration_value * minute_map.get(operation.duration_unit, 0.0)
            operation.duration_days = operation.duration_minutes / (8.0 * 60.0)
