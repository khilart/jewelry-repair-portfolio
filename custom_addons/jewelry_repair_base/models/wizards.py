from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError


class AcceptItemWizard(models.TransientModel):
    _name = "jewelry.accept.item.wizard"
    _description = "Accept Item Wizard"

    operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        required=True,
        ondelete="cascade",
        readonly=True,
    )
    weight_before = fields.Float(string="Weight Before Work (g)", digits=(16, 3))

    def action_confirm(self):
        self.ensure_one()
        operation = self.operation_id
        if operation.state != "ready":
            raise UserError(_("Only ready operations can be accepted."))
        operation._check_assignee_access()
        operation.write({
            "state": "accepted",
            "accepted_by_user_id": self.env.user.id,
            "accepted_at": fields.Datetime.now(),
            "assigned_user_id": operation.assigned_user_id.id or self.env.user.id,
            "executor_id": operation.executor_id.id
            or self.env["jewelry.repair.executor"]._find_for_user(
                operation.assigned_user_id or self.env.user
            ).id,
            "weight_before": self.weight_before,
        })
        operation.order_id._set_current_holder(self.env.user, "in_work")


class MetalLossReportWizard(models.TransientModel):
    _name = "jewelry.metal.loss.report.wizard"
    _description = "Metal Loss Report Wizard"

    date_from = fields.Date(string="From", required=True,
                            default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string="To", required=True,
                          default=fields.Date.today)
    report_type = fields.Selection([
        ("by_operation", "By Operation Type"),
        ("by_executor", "By Executor"),
    ], string="Group By", required=True, default="by_operation")

    def action_print(self):
        self.ensure_one()
        report_name = (
            "jewelry_repair_base.report_metal_loss_by_operation"
            if self.report_type == "by_operation"
            else "jewelry_repair_base.report_metal_loss_by_executor"
        )
        return self.env.ref(report_name).report_action(self)

    def _get_loss_data(self):
        """
        Returns list of dicts:
        {
            operation_name, is_gem_setting,
            executor_name, order_name, partner_name,
            weight_loss,   # negative = actual loss, positive = gem gain
            is_gem_block,  # True for the grouped gem-setting row
        }
        """
        self.ensure_one()
        ops = self.env["jewelry.repair.order.operation"].search([
            ("state", "=", "done"),
            ("done_at", ">=", fields.Datetime.from_string(str(self.date_from))),
            ("done_at", "<=", fields.Datetime.from_string(str(self.date_to) + " 23:59:59")),
            ("weight_before", ">", 0),
        ], order="order_id, sequence, id")

        # Group by order
        by_order = defaultdict(list)
        for op in ops:
            by_order[op.order_id].append(op)

        rows = []
        for order, order_ops in by_order.items():
            gem_weight = order.gem_weight_total_g or 0.0

            # Find gem-setting block boundaries
            gem_indices = [
                i for i, op in enumerate(order_ops)
                if op.operation_id.is_gem_setting
            ]
            gem_block_end = max(gem_indices) if gem_indices else -1

            gem_block_added = False

            for i, op in enumerate(order_ops):
                is_gem = op.operation_id.is_gem_setting

                # Weight at end of this operation
                if i + 1 < len(order_ops):
                    raw_next = order_ops[i + 1].weight_before
                else:
                    raw_next = order.delivered_weight

                # Adjust weights after gem block
                adj_current = op.weight_before - (gem_weight if i > gem_block_end else 0.0)
                adj_next = raw_next - (gem_weight if (i + 1) > gem_block_end else 0.0)

                if is_gem:
                    # Accumulate gem rows into one block at the end of gem sequence
                    if not gem_block_added and i == gem_block_end:
                        # First op in gem block → find its weight_before
                        gem_start_weight = order_ops[gem_indices[0]].weight_before
                        rows.append({
                            "operation_name": _("Gem Setting"),
                            "is_gem_block": True,
                            "executor_name": op.assigned_user_id.name or "—",
                            "order_name": order.name,
                            "partner_name": order.partner_id.name or "—",
                            "weight_loss": 0.0,       # not a metal loss
                            "gem_weight": gem_weight,
                        })
                        gem_block_added = True
                    continue

                loss = adj_current - adj_next
                rows.append({
                    "operation_name": op.operation_id.name or op.name or "—",
                    "is_gem_block": False,
                    "executor_name": op.assigned_user_id.name or "—",
                    "order_name": order.name,
                    "partner_name": order.partner_id.name or "—",
                    "weight_loss": loss,
                    "gem_weight": 0.0,
                })

        return rows

    def _get_grouped_by_operation(self):
        rows = self._get_loss_data()
        groups = defaultdict(lambda: {"loss": 0.0, "count": 0, "gem_weight": 0.0, "is_gem_block": False})
        for r in rows:
            key = r["operation_name"]
            groups[key]["loss"] += r["weight_loss"]
            groups[key]["count"] += 1
            groups[key]["gem_weight"] += r.get("gem_weight", 0.0)
            groups[key]["is_gem_block"] = r["is_gem_block"]
        return sorted(groups.items(), key=lambda x: (x[1]["is_gem_block"], x[0]))

    def _get_grouped_by_executor(self):
        rows = self._get_loss_data()
        groups = defaultdict(lambda: {"loss": 0.0, "count": 0})
        for r in rows:
            if r["is_gem_block"]:
                continue
            groups[r["executor_name"]]["loss"] += r["weight_loss"]
            groups[r["executor_name"]]["count"] += 1
        return sorted(groups.items(), key=lambda x: x[0])
