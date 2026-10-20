import logging

from odoo import fields, models
from .jewelry_repair_order import _is_enabled, _get_token, _is_working_time, _send_message, _format_dt

_logger = logging.getLogger(__name__)


def _build_assign_text(env, op):
    order = op.order_id
    deadline_str = _format_dt(env, order.deadline_date)
    base_url = env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
    action_id = env.ref("jewelry_repair_base.action_jewelry_repair_order_operation_master").id
    my_work_url = f"{base_url}/odoo/action-{action_id}"
    return (
        f"🔨 <b>Новая задача</b>\n\n"
        f"Заказ: {order.name}\n"
        f"Изделие: {order.item_type_id.name or ''}\n"
        f"Операция: {op.operation_id.name}\n"
        f"Клиент: {order.partner_id.name}\n"
        f"Дедлайн: {deadline_str}\n\n"
        f'<a href="{my_work_url}">Открыть My Work</a>'
    )


class JewelryRepairOrderOperation(models.Model):
    _inherit = "jewelry.repair.order.operation"

    assign_notify_pending = fields.Boolean(
        string="Assignment Notification Pending",
        default=False,
        copy=False,
    )

    def write(self, vals):
        notify_candidates = []
        if "assigned_user_id" in vals or "state" in vals:
            for op in self:
                notify_candidates.append((op, op.assigned_user_id.id, op.state))

        result = super().write(vals)

        # Clear pending flag if operation finished before morning notification arrived
        if "state" in vals and vals["state"] in ("done", "cancel"):
            self.filtered("assign_notify_pending").write({"assign_notify_pending": False})

        if not _is_enabled(self.env, "jewelry_telegram.notify_operation_assigned"):
            return result

        token = _get_token(self.env)
        if not token:
            return result

        working = _is_working_time(self.env)

        for op, prev_assigned, prev_state in notify_candidates:
            if op.state in ("done", "cancel"):
                continue
            new_user = op.assigned_user_id
            if not new_user or not new_user.telegram_chat_id:
                continue
            assignment_changed = new_user.id != prev_assigned
            became_active = op.state == "ready" and prev_state == "pending"
            if not (assignment_changed or became_active):
                continue

            if working:
                text = _build_assign_text(self.env, op)
                _send_message(self.env, token, new_user.telegram_chat_id, text)
            else:
                op.write({"assign_notify_pending": True})

        return result

    def _send_pending_assign_notifications(self):
        """Send deferred assignment notifications. Called at the start of morning cron."""
        if not _is_enabled(self.env, "jewelry_telegram.notify_operation_assigned"):
            return
        token = _get_token(self.env)
        if not token:
            return

        pending = self.search([
            ("assign_notify_pending", "=", True),
            ("state", "not in", ("done", "cancel")),
            ("assigned_user_id", "!=", False),
        ])
        for op in pending:
            user = op.assigned_user_id
            if not user.telegram_chat_id:
                continue
            text = _build_assign_text(self.env, op)
            _send_message(self.env, token, user.telegram_chat_id, text)

        pending.write({"assign_notify_pending": False})
