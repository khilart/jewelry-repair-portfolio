from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_chat_id = fields.Char(
        string="Telegram Chat ID",
        help="Telegram chat ID for push notifications. "
             "To get your ID: write any message to the bot, then ask your manager to look it up.",
    )
    inactivity_notified_at = fields.Datetime(
        string="Last Inactivity Notification",
        readonly=True,
        copy=False,
    )
