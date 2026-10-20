import logging
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from . import telegram_service

_logger = logging.getLogger(__name__)


def _format_dt(env, dt):
    """Format a UTC datetime using the configured notification timezone."""
    if not dt:
        return "—"
    tz_name = env["ir.config_parameter"].sudo().get_param("jewelry_telegram.timezone", "Europe/Brussels")
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    return pytz.utc.localize(dt).astimezone(tz).strftime('%d.%m %H:%M')


def _get_param(env, key, default=None):
    return env["ir.config_parameter"].sudo().get_param(key, default)


def _is_enabled(env, key):
    return _get_param(env, key) == "True"


def _get_active_weekdays(env):
    params = env["ir.config_parameter"].sudo()
    day_params = [
        (0, "jewelry_telegram.inactivity_mon"),
        (1, "jewelry_telegram.inactivity_tue"),
        (2, "jewelry_telegram.inactivity_wed"),
        (3, "jewelry_telegram.inactivity_thu"),
        (4, "jewelry_telegram.inactivity_fri"),
        (5, "jewelry_telegram.inactivity_sat"),
        (6, "jewelry_telegram.inactivity_sun"),
    ]
    active = set()
    for weekday, param_key in day_params:
        if params.get_param(param_key, "True" if weekday < 5 else "False") not in ("False", "0", ""):
            active.add(weekday)
    return active


def _is_working_day(env):
    """Return True if today is a configured working day."""
    params = env["ir.config_parameter"].sudo()
    tz_name = params.get_param("jewelry_telegram.timezone", "Europe/Brussels")
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC

    import datetime as dt
    now_local = dt.datetime.now(tz)
    return now_local.weekday() in _get_active_weekdays(env)


def _is_working_time(env):
    """Return True if current moment falls within configured working days and hours."""
    params = env["ir.config_parameter"].sudo()
    work_start = int(params.get_param("jewelry_telegram.work_hours_start", 10))
    work_end = int(params.get_param("jewelry_telegram.work_hours_end", 18))

    tz_name = params.get_param("jewelry_telegram.timezone", "Europe/Brussels")
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC

    import datetime as dt
    now_local = dt.datetime.now(tz)
    if now_local.weekday() not in _get_active_weekdays(env):
        return False
    if not (work_start <= now_local.hour < work_end):
        return False
    return True


def _get_token(env):
    return _get_param(env, "jewelry_telegram.bot_token")


def _send_message(env, token, chat_id, text):
    """Send message, redirecting to test chat_id if set in context."""
    target = env.context.get("test_notification_chat_id") or chat_id
    telegram_service.send_message(token, target, text)


def _notify_users(env, users, text):
    token = _get_token(env)
    if not token:
        return
    test_chat_id = env.context.get("test_notification_chat_id")
    if test_chat_id:
        telegram_service.send_message(token, test_chat_id, text)
    else:
        for user in users.filtered(lambda u: u.telegram_chat_id):
            telegram_service.send_message(token, user.telegram_chat_id, text)


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    deadline_notified = fields.Boolean(
        string="Deadline Notification Sent",
        default=False,
        copy=False,
    )
    overdue_notified_date = fields.Date(
        string="Last Overdue Notification Date",
        copy=False,
    )
    morning_digest_sent_date = fields.Date(
        string="Morning Digest Sent Date",
        copy=False,
    )

    @api.onchange("deadline_date")
    def _onchange_deadline_date_reset_notify(self):
        self.deadline_notified = False

    def write(self, vals):
        if "deadline_date" in vals:
            super_vals = dict(vals, deadline_notified=False)
        else:
            super_vals = vals
        return super().write(super_vals)

    def action_mark_ready(self):
        result = super().action_mark_ready()
        if _is_enabled(self.env, "jewelry_telegram.notify_order_ready"):
            managers = self.env.ref("jewelry_repair_base.group_jewelry_repair_manager").users
            for order in self.filtered(lambda o: o.state == "ready"):
                text = (
                    f"✅ <b>Заказ готов к приёмке</b>\n\n"
                    f"Заказ: {order.name}\n"
                    f"Изделие: {order.item_type_id.name or ''}\n"
                    f"Клиент: {order.partner_id.name}"
                )
                _notify_users(self.env, managers, text)
        return result

    def action_accept_ready_item(self):
        result = super().action_accept_ready_item()
        if _is_enabled(self.env, "jewelry_telegram.notify_order_delivery_ready"):
            receptionists = self.env.ref("jewelry_repair_base.group_jewelry_repair_receptionist").users
            for order in self.filtered(lambda o: o.state == "ready_for_delivery"):
                text = (
                    f"📦 <b>Заказ готов к выдаче</b>\n\n"
                    f"Заказ: {order.name}\n"
                    f"Изделие: {order.item_type_id.name or ''}\n"
                    f"Клиент: {order.partner_id.name}"
                )
                _notify_users(self.env, receptionists, text)
        return result

    @api.model
    def _cron_morning_digest(self):
        test_mode = bool(self.env.context.get("test_notification_chat_id"))

        # Send deferred assignment notifications first
        if not test_mode:
            self.env["jewelry.repair.order.operation"]._send_pending_assign_notifications()

        if not test_mode and not _is_enabled(self.env, "jewelry_telegram.notify_morning_digest"):
            return
        if not test_mode and not _is_working_day(self.env):
            return
        token = _get_token(self.env)
        if not token:
            return

        today = fields.Date.today()
        active_states = ["in_progress", "ready", "accepted"]

        orders = self.search([
            ("state", "in", active_states),
            ("deadline_date", "!=", False),
            ("deadline_date", ">=", fields.Datetime.to_string(today)),
            ("deadline_date", "<", fields.Datetime.to_string(today + timedelta(days=1))),
        ]).filtered(lambda o: not o.morning_digest_sent_date or o.morning_digest_sent_date < today)

        if not orders:
            return

        # Group by master
        master_orders = {}
        for order in orders:
            active_ops = order.order_operation_ids.filtered(
                lambda o: o.state not in ("done", "cancel") and o.assigned_user_id
            )
            for op in active_ops:
                user = op.assigned_user_id
                if not user.telegram_chat_id:
                    continue
                master_orders.setdefault(user, [])
                if order not in master_orders[user]:
                    master_orders[user].append(order)

        for user, user_orders in master_orders.items():
            lines = "\n".join(
                f"• {o.name} — {o.item_type_id.name or ''} | {o.partner_id.name} "
                f"(дедлайн: {_format_dt(self.env, o.deadline_date)})"
                for o in user_orders
            )
            text = f"📋 <b>Дедлайны на сегодня</b>\n\n{lines}"
            _send_message(self.env, token, user.telegram_chat_id, text)

        # Manager digest — all today's orders regardless of assignment
        def _order_line(o):
            active_ops = o.order_operation_ids.filtered(lambda op: op.state not in ("done", "cancel"))
            assigned = active_ops.filtered(lambda op: op.assigned_user_id)
            masters_str = ", ".join(dict.fromkeys(
                op.assigned_user_id.name for op in assigned
            )) or "⚠️ не назначен"
            deadline_str = _format_dt(self.env, o.deadline_date)
            return f"• {o.name} — {o.item_type_id.name or ''} | {o.partner_id.name} | {masters_str} | дедлайн: {deadline_str}"

        manager_text = f"📋 <b>Дедлайны на сегодня (менеджер)</b>\n\n" + "\n".join(_order_line(o) for o in orders)
        test_chat_id = self.env.context.get("test_notification_chat_id")
        if test_chat_id:
            telegram_service.send_message(token, test_chat_id, manager_text)
        else:
            managers = self.env.ref("jewelry_repair_base.group_jewelry_repair_manager").users.filtered(
                lambda u: u.telegram_chat_id
            )
            for manager in managers:
                telegram_service.send_message(token, manager.telegram_chat_id, manager_text)

        if not self.env.context.get("test_notification_chat_id"):
            orders.write({"morning_digest_sent_date": today})

    @api.model
    def _cron_check_deadlines(self):
        now = fields.Datetime.now()
        test_mode = bool(self.env.context.get("test_notification_chat_id"))
        if not test_mode and not _is_working_time(self.env):
            return
        active_states = ["draft", "in_progress"]

        # --- Deadline approaching (within 1.5 hours, future only) ---
        if test_mode or _is_enabled(self.env, "jewelry_telegram.notify_deadline_approaching"):
            window_end = now + timedelta(hours=1, minutes=30)
            orders = self.search([
                ("state", "in", active_states),
                ("deadline_date", "!=", False),
                ("deadline_date", ">", now),
                ("deadline_date", "<=", window_end),
                ("deadline_notified", "=", False),
            ])
            managers = self.env.ref("jewelry_repair_base.group_jewelry_repair_manager").users
            for order in orders:
                deadline_str = _format_dt(self.env, order.deadline_date)

                # Notify masters with active operations
                active_ops = order.order_operation_ids.filtered(
                    lambda o: o.state not in ("done", "cancel") and o.assigned_user_id
                )
                for op in active_ops:
                    user = op.assigned_user_id
                    if not user.telegram_chat_id:
                        continue
                    text = (
                        f"⚠️ <b>Дедлайн через час</b>\n\n"
                        f"Заказ: {order.name}\n"
                        f"Изделие: {order.item_type_id.name or ''}\n"
                        f"Операция: {op.operation_id.name}\n"
                        f"Дедлайн: {deadline_str}"
                    )
                    _send_message(self.env, _get_token(self.env), user.telegram_chat_id, text)

                # Notify managers
                manager_text = (
                    f"⚠️ <b>Дедлайн через час</b>\n\n"
                    f"Заказ: {order.name} — {order.item_type_id.name or ''}\n"
                    f"Клиент: {order.partner_id.name}\n"
                    f"Дедлайн: {deadline_str}"
                )
                _notify_users(self.env, managers, manager_text)

                if not self.env.context.get("test_notification_chat_id"):
                    order.deadline_notified = True

        # --- Overdue orders ---
        if test_mode or _is_enabled(self.env, "jewelry_telegram.notify_order_overdue"):
            today = fields.Date.today()
            orders = self.search([
                ("state", "in", active_states),
                ("deadline_date", "!=", False),
                ("deadline_date", "<", now),
            ]).filtered(
                lambda o: not o.overdue_notified_date or o.overdue_notified_date < today
            )
            managers = self.env.ref("jewelry_repair_base.group_jewelry_repair_manager").users
            for order in orders:
                deadline_str = _format_dt(self.env, order.deadline_date)
                text = (
                    f"🚨 <b>Заказ просрочен</b>\n\n"
                    f"Заказ: {order.name}\n"
                    f"Изделие: {order.item_type_id.name or ''}\n"
                    f"Клиент: {order.partner_id.name}\n"
                    f"Дедлайн был: {deadline_str}"
                )
                _notify_users(self.env, managers, text)
                if not self.env.context.get("test_notification_chat_id"):
                    order.overdue_notified_date = today
