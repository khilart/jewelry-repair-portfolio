from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ClientMetalAccount(models.Model):
    _name = "jewelry.client.metal.account"
    _description = "Client Metal Account"
    _order = "partner_id, metal_id"
    _rec_name = "display_name"

    partner_id = fields.Many2one("res.partner", string="Client", required=True, index=True)
    metal_id = fields.Many2one("jewelry.metal", string="Metal", required=True, index=True)
    display_name = fields.Char(compute="_compute_display_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    active = fields.Boolean(default=True)

    balance_fine = fields.Float(
        string="Balance (fine g)",
        compute="_compute_balance_fine",
        store=True,
        digits=(16, 4),
        readonly=True,
    )
    balance_18k = fields.Float(
        string="18k (g)",
        compute="_compute_balance_by_alloy",
        digits=(16, 2),
    )
    balance_14k = fields.Float(
        string="14k (g)",
        compute="_compute_balance_by_alloy",
        digits=(16, 2),
    )
    balance_9k = fields.Float(
        string="9k (g)",
        compute="_compute_balance_by_alloy",
        digits=(16, 2),
    )
    transaction_ids = fields.One2many(
        "jewelry.client.metal.transaction",
        "account_id",
        string="Transactions",
    )

    _sql_constraints = [
        (
            "partner_metal_company_unique",
            "unique(partner_id, metal_id, company_id)",
            "A client metal account for this client and metal already exists in this company.",
        )
    ]

    @api.depends("partner_id.name", "metal_id.name")
    def _compute_display_name(self):
        for account in self:
            account.display_name = f"{account.partner_id.name or ''} — {account.metal_id.name or ''}"

    @api.depends("transaction_ids.weight_fine", "transaction_ids.state")
    def _compute_balance_fine(self):
        for account in self:
            account.balance_fine = sum(
                t.weight_fine
                for t in account.transaction_ids
                if t.state == "posted"
            )

    @api.depends("balance_fine")
    def _compute_balance_by_alloy(self):
        for account in self:
            fine = account.balance_fine
            account.balance_18k = fine / 0.750 if fine else 0.0
            account.balance_14k = fine / 0.585 if fine else 0.0
            account.balance_9k  = fine / 0.375 if fine else 0.0

    def get_balance_in_alloys(self):
        self.ensure_one()
        alloys = self.env["jewelry.metal.alloy"].search([
            ("metal_id", "=", self.metal_id.id),
            ("show_in_client_balance", "=", True),
            ("active", "=", True),
        ])
        result = []
        for alloy in alloys:
            if alloy.purity:
                result.append({
                    "alloy": alloy,
                    "weight": self.balance_fine / alloy.purity,
                })
        return result


class ClientMetalTransaction(models.Model):
    _name = "jewelry.client.metal.transaction"
    _description = "Client Metal Transaction"
    _order = "transaction_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="/")

    account_id = fields.Many2one(
        "jewelry.client.metal.account",
        string="Account",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        related="account_id.partner_id",
        store=True,
        index=True,
        readonly=True,
    )
    metal_id = fields.Many2one(
        related="account_id.metal_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="account_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="account_id.currency_id",
        store=True,
        readonly=True,
    )

    transaction_type = fields.Selection(
        [
            ("deposit_metal", "Metal Deposit"),
            ("deposit_cash", "Cash Deposit"),
            ("debit_repair", "Repair Debit"),
            ("credit_return", "Metal Return"),
            ("adjustment", "Adjustment"),
        ],
        string="Type",
        required=True,
        index=True,
    )
    transaction_date = fields.Datetime(
        string="Date",
        required=True,
        default=lambda self: self._user_now(),
        index=True,
    )
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy")
    weight_alloy = fields.Float(string="Alloy Weight (g)", digits=(16, 3))
    purity = fields.Float(string="Purity", digits=(16, 6))
    weight_fine = fields.Float(string="Fine Weight (g)", digits=(16, 4))
    rate_datetime = fields.Datetime(string="Rate Date", default=lambda self: self._user_now())
    rate_price_per_gram = fields.Monetary(
        string="Rate (per g fine)",
        currency_field="currency_id",
    )
    money_equivalent = fields.Monetary(
        string="Money Equivalent",
        currency_field="currency_id",
    )
    state = fields.Selection(
        [("posted", "Posted"), ("cancelled", "Cancelled")],
        string="Status",
        default="posted",
        required=True,
        index=True,
    )
    notes = fields.Text(string="Notes")
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source ID", readonly=True)
    source_ref = fields.Char(string="Source Reference", readonly=True)
    receipt_id = fields.Many2one(
        "jewelry.client.metal.receipt",
        string="Receipt",
        readonly=True,
        ondelete="set null",
        index=True,
    )

    def _user_now(self):
        tz_name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        user_tz = pytz.timezone(tz_name)
        return datetime.now(user_tz).replace(tzinfo=None)

    def _get_metal_rate(self, metal, at_datetime):
        if not metal or not at_datetime:
            return self.env["jewelry.metal.rate"].browse()
        return self.env["jewelry.metal.rate"]._get_latest_rate(metal, at_datetime, self.env.company)

    @api.onchange("alloy_id")
    def _onchange_alloy_id(self):
        if self.alloy_id:
            self.purity = self.alloy_id.purity
        self._fill_rate_from_registry()

    @api.onchange("rate_datetime", "account_id")
    def _onchange_rate_datetime(self):
        self._fill_rate_from_registry()

    def _fill_rate_from_registry(self):
        metal = self.account_id.metal_id if self.account_id else False
        if not metal:
            return
        if not self.rate_datetime:
            self.rate_datetime = self._user_now()
        rate = self._get_metal_rate(metal, self.rate_datetime)
        if rate:
            self.rate_price_per_gram = rate.price_per_gram

    @api.onchange("weight_alloy", "purity", "transaction_type")
    def _onchange_weight_fine(self):
        if self.transaction_type in ("deposit_metal", "debit_repair", "credit_return"):
            fine = (self.weight_alloy or 0.0) * (self.purity or 0.0)
            if self.transaction_type in ("debit_repair", "credit_return"):
                fine = -fine
            self.weight_fine = fine

    @api.onchange("money_equivalent", "rate_price_per_gram")
    def _onchange_money_to_fine(self):
        if self.transaction_type == "deposit_cash" and self.rate_price_per_gram:
            self.weight_fine = (self.money_equivalent or 0.0) / self.rate_price_per_gram

    @api.onchange("weight_fine")
    def _onchange_fine_to_money(self):
        if self.transaction_type == "deposit_cash" and self.rate_price_per_gram:
            self.money_equivalent = (self.weight_fine or 0.0) * self.rate_price_per_gram

    @api.constrains("weight_fine", "transaction_type")
    def _check_weight_fine_sign(self):
        for t in self:
            if t.transaction_type in ("debit_repair", "credit_return") and t.weight_fine > 0:
                raise ValidationError(
                    _("Fine weight must be negative for debit and return transactions.")
                )
            if t.transaction_type in ("deposit_metal", "deposit_cash") and t.weight_fine < 0:
                raise ValidationError(
                    _("Fine weight must be positive for deposit transactions.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("jewelry.client.metal.transaction") or "/"
        return super().create(vals_list)

    def action_open_source(self):
        self.ensure_one()
        if self.receipt_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "jewelry.client.metal.receipt",
                "res_id": self.receipt_id.id,
                "view_mode": "form",
                "target": "current",
            }
        if self.source_model and self.source_res_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": self.source_model,
                "res_id": self.source_res_id,
                "view_mode": "form",
                "target": "current",
            }
        raise UserError(_("No source document linked to this transaction."))

    def action_cancel(self):
        for t in self:
            if t.state == "cancelled":
                raise UserError(_("Transaction is already cancelled."))
            t.state = "cancelled"

    def action_repost(self):
        for t in self:
            if t.state == "posted":
                raise UserError(_("Transaction is already posted."))
            t.state = "posted"
