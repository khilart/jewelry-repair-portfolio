import logging
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from .jewelry_repair_order import _is_enabled, _get_token, _send_message

_logger = logging.getLogger(__name__)


class JewelryRepairOrderOperationInactivity(models.Model):
    _inherit = "jewelry.repair.order.operation"

    @api.model
    def _cron_check_master_inactivity(self):
        test_mode = bool(self.env.context.get("test_notification_chat_id"))
        if not test_mode and not _is_enabled(self.env, "jewelry_telegram.notify_master_inactivity"):
            return

        token = _get_token(self.env)
        if not token:
            return

        params = self.env["ir.config_parameter"].sudo()
        threshold_hours = int(params.get_param("jewelry_telegram.inactivity_threshold_hours", 1))
        work_start = int(params.get_param("jewelry_telegram.work_hours_start", 10))
        work_end = int(params.get_param("jewelry_telegram.work_hours_end", 18))

        active_weekdays = set()
        day_params = [
            (0, "jewelry_telegram.inactivity_mon"),
            (1, "jewelry_telegram.inactivity_tue"),
            (2, "jewelry_telegram.inactivity_wed"),
            (3, "jewelry_telegram.inactivity_thu"),
            (4, "jewelry_telegram.inactivity_fri"),
            (5, "jewelry_telegram.inactivity_sat"),
            (6, "jewelry_telegram.inactivity_sun"),
        ]
        for weekday, param_key in day_params:
            if params.get_param(param_key, "True" if weekday < 5 else "False") not in ("False", "0", ""):
                active_weekdays.add(weekday)

        now_utc = datetime.utcnow()

        users = self.env["res.users"].search([("telegram_chat_id", "!=", False)])
        for user in users:
            tz_name = user.tz or "UTC"
            try:
                user_tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.UTC

            now_local = datetime.now(user_tz)
            if now_local.weekday() not in active_weekdays:
                continue
            if not (work_start <= now_local.hour < work_end):
                continue

            # Has something to start
            ready_ops = self.env["jewelry.repair.order.operation"].search([
                ("assigned_user_id", "=", user.id),
                ("state", "in", ["ready", "accepted"]),
            ], limit=1)
            if not ready_ops:
                continue

            # Nothing started in the last threshold_hours
            cutoff = now_utc - timedelta(hours=threshold_hours)
            recently_started = self.env["jewelry.repair.order.operation"].search([
                ("assigned_user_id", "=", user.id),
                ("started_at", ">=", fields.Datetime.to_string(cutoff)),
            ], limit=1)
            if recently_started:
                continue

            # Not notified recently
            if user.inactivity_notified_at:
                last = fields.Datetime.from_string(user.inactivity_notified_at)
                if (now_utc - last).total_seconds() < threshold_hours * 3600:
                    continue

            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
            action_id = self.env.ref("jewelry_repair_base.action_jewelry_repair_order_operation_master").id
            my_work_url = f"{base_url}/odoo/action-{action_id}"
            text = (
                f"⏰ <b>Напоминание</b>\n\n"
                f"У вас есть операции, готовые к старту.\n"
                f"Не забудьте отметить начало работы в системе.\n\n"
                f'<a href="{my_work_url}">Открыть My Work</a>'
            )
            _send_message(self.env, token, user.telegram_chat_id, text)
            if not self.env.context.get("test_notification_chat_id"):
                user.sudo().write({"inactivity_notified_at": fields.Datetime.now()})
            _logger.info("Inactivity reminder sent to user %s (%s)", user.name, user.telegram_chat_id)
