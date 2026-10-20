import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from . import telegram_service

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    telegram_bot_token = fields.Char(
        string="Bot Token",
        config_parameter="jewelry_telegram.bot_token",
    )
    telegram_notify_operation_assigned = fields.Boolean(
        string="New operation assigned to master",
        config_parameter="jewelry_telegram.notify_operation_assigned",
    )
    telegram_notify_morning_digest = fields.Boolean(
        string="Morning digest of today's deadlines",
        config_parameter="jewelry_telegram.notify_morning_digest",
    )
    telegram_notify_deadline_approaching = fields.Boolean(
        string="Notify 1 hour before deadline",
        config_parameter="jewelry_telegram.notify_deadline_approaching",
    )
    telegram_notify_order_overdue = fields.Boolean(
        string="Order overdue",
        config_parameter="jewelry_telegram.notify_order_overdue",
    )
    telegram_notify_order_ready = fields.Boolean(
        string="Order moved to Ready",
        config_parameter="jewelry_telegram.notify_order_ready",
    )
    telegram_notify_order_delivery_ready = fields.Boolean(
        string="Order ready for delivery",
        config_parameter="jewelry_telegram.notify_order_delivery_ready",
    )
    telegram_timezone = fields.Selection(
        string="Timezone",
        selection="_tz_get",
        config_parameter="jewelry_telegram.timezone",
        default="Europe/Brussels",
        help="Timezone for formatting dates in Telegram notifications.",
    )

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in sorted(pytz.all_timezones)]
    telegram_test_chat_id = fields.Char(
        string="Test Chat ID",
        config_parameter="jewelry_telegram.test_chat_id",
        help="Telegram Chat ID for debug testing. All test notifications will be sent here.",
    )
    telegram_notify_master_inactivity = fields.Boolean(
        string="Remind master if idle during working hours",
        config_parameter="jewelry_telegram.notify_master_inactivity",
    )
    telegram_inactivity_threshold_hours = fields.Integer(
        string="Inactivity threshold (hours)",
        config_parameter="jewelry_telegram.inactivity_threshold_hours",
        default=1,
    )
    telegram_work_hours_start = fields.Integer(
        string="Working hours start",
        config_parameter="jewelry_telegram.work_hours_start",
        default=10,
    )
    telegram_work_hours_end = fields.Integer(
        string="Working hours end",
        config_parameter="jewelry_telegram.work_hours_end",
        default=18,
    )
    telegram_inactivity_mon = fields.Boolean(
        string="Monday", config_parameter="jewelry_telegram.inactivity_mon", default=True,
    )
    telegram_inactivity_tue = fields.Boolean(
        string="Tuesday", config_parameter="jewelry_telegram.inactivity_tue", default=True,
    )
    telegram_inactivity_wed = fields.Boolean(
        string="Wednesday", config_parameter="jewelry_telegram.inactivity_wed", default=True,
    )
    telegram_inactivity_thu = fields.Boolean(
        string="Thursday", config_parameter="jewelry_telegram.inactivity_thu", default=True,
    )
    telegram_inactivity_fri = fields.Boolean(
        string="Friday", config_parameter="jewelry_telegram.inactivity_fri", default=True,
    )
    telegram_inactivity_sat = fields.Boolean(
        string="Saturday", config_parameter="jewelry_telegram.inactivity_sat", default=False,
    )
    telegram_inactivity_sun = fields.Boolean(
        string="Sunday", config_parameter="jewelry_telegram.inactivity_sun", default=False,
    )
    def _get_test_chat_id(self):
        chat_id = self.env["ir.config_parameter"].sudo().get_param("jewelry_telegram.test_chat_id")
        if not chat_id:
            raise UserError(_("Test Chat ID is not set. Fill it in the Debug section first."))
        return chat_id

    def action_test_morning_digest(self):
        chat_id = self._get_test_chat_id()
        self.env["jewelry.repair.order"].with_context(
            test_notification_chat_id=chat_id
        )._cron_morning_digest()

    def action_test_deadlines(self):
        chat_id = self._get_test_chat_id()
        self.env["jewelry.repair.order"].with_context(
            test_notification_chat_id=chat_id
        )._cron_check_deadlines()

    def action_test_master_inactivity(self):
        chat_id = self._get_test_chat_id()
        self.env["jewelry.repair.order.operation"].with_context(
            test_notification_chat_id=chat_id
        )._cron_check_master_inactivity()

    def action_test_telegram(self):
        self.ensure_one()
        token = self.telegram_bot_token or self.env["ir.config_parameter"].sudo().get_param("jewelry_telegram.bot_token")
        chat_id = self.env.user.telegram_chat_id
        ok, error = telegram_service.test_connection(token, chat_id)
        if ok:
            msg = _("Test message sent successfully!")
            msg_type = "success"
        else:
            msg = error or _("Failed to send test message.")
            msg_type = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Telegram Test"),
                "message": msg,
                "type": msg_type,
                "sticky": False,
            },
        }
