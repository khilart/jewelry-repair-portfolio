from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ClientMetalReceipt(models.Model):
    _name = "jewelry.client.metal.receipt"
    _description = "Client Metal Receipt"
    _order = "operation_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="/")
    operation_type = fields.Selection(
        [
            ("deposit_metal", "Metal Deposit"),
            ("deposit_cash", "Cash Deposit"),
            ("credit_return", "Metal Return"),
            ("adjustment", "Adjustment"),
        ],
        string="Type",
        required=True,
        index=True,
    )
    partner_id = fields.Many2one("res.partner", string="Client", required=True, index=True)
    account_id = fields.Many2one(
        "jewelry.client.metal.account",
        string="Account",
        required=True,
        domain="[('partner_id', '=', partner_id), ('active', '=', True)]",
        index=True,
    )
    metal_id = fields.Many2one(related="account_id.metal_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="account_id.currency_id", store=True, readonly=True)
    company_id = fields.Many2one(related="account_id.company_id", store=True, readonly=True)
    account_balance_fine = fields.Float(
        related="account_id.balance_fine",
        string="Account Balance (fine g)",
        digits=(16, 4),
        readonly=True,
    )
    operation_date = fields.Datetime(
        string="Date",
        required=True,
        default=lambda self: self._user_now(),
        index=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")],
        string="Status",
        default="draft",
        required=True,
        index=True,
    )
    storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Storage",
        domain="[('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many(
        "jewelry.client.metal.receipt.line",
        "receipt_id",
        string="Lines",
    )
    metal_document_id = fields.Many2one(
        "jewelry.metal.document",
        string="Metal Document",
        readonly=True,
        copy=False,
    )
    transaction_ids = fields.One2many(
        "jewelry.client.metal.transaction",
        "receipt_id",
        string="Transactions",
        readonly=True,
    )
    notes = fields.Text(string="Notes")

    def _user_now(self):
        tz_name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        user_tz = pytz.timezone(tz_name)
        return datetime.now(user_tz).replace(tzinfo=None)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.account_id = False
        if self.partner_id:
            accounts = self.env["jewelry.client.metal.account"].search([
                ("partner_id", "=", self.partner_id.id),
                ("active", "=", True),
            ])
            if len(accounts) == 1:
                self.account_id = accounts

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("jewelry.client.metal.receipt") or "/"
                )
        return super().create(vals_list)

    def _validate(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one line before confirming."))
        if self.operation_type in ("deposit_metal", "credit_return") and not self.storage_id:
            raise UserError(_("Storage is required for metal deposit and return operations."))
        for line in self.line_ids:
            if self.operation_type == "deposit_cash":
                if not line.money_equivalent:
                    raise UserError(_("Money equivalent is required for cash deposit lines."))
            else:
                if not line.alloy_id:
                    raise UserError(_("Alloy is required on each line."))
                if not line.weight_alloy:
                    raise UserError(_("Alloy weight cannot be zero."))
            if not line.weight_fine:
                raise UserError(_("Fine weight cannot be zero."))

    def _create_metal_document(self):
        self.ensure_one()
        metal_op = "receipt" if self.operation_type == "deposit_metal" else "writeoff"
        storage_field = "dest_storage_id" if metal_op == "receipt" else "source_storage_id"
        doc = self.env["jewelry.metal.document"].create({
            "operation_type": metal_op,
            "partner_id": self.partner_id.id,
            storage_field: self.storage_id.id,
            "document_date": self.operation_date,
            "company_id": self.company_id.id,
            "line_ids": [
                (0, 0, {"alloy_id": line.alloy_id.id, "weight": line.weight_alloy})
                for line in self.line_ids
                if line.alloy_id and line.weight_alloy
            ],
        })
        doc.action_post()
        self.metal_document_id = doc

    def _create_transactions(self):
        self.ensure_one()
        sign = -1 if self.operation_type == "credit_return" else 1
        vals_list = []
        for line in self.line_ids:
            # An adjustment goes either way: its sign is the one the user entered.
            if self.operation_type == "adjustment":
                weight_fine = line.weight_fine
            else:
                weight_fine = abs(line.weight_fine) * sign
            vals_list.append({
                "account_id": self.account_id.id,
                "transaction_type": self.operation_type,
                "transaction_date": self.operation_date,
                "alloy_id": line.alloy_id.id if line.alloy_id else False,
                "weight_alloy": line.weight_alloy,
                "purity": line.purity,
                "weight_fine": weight_fine,
                "rate_datetime": line.rate_datetime,
                "rate_price_per_gram": line.rate_price_per_gram,
                "money_equivalent": line.money_equivalent,
                "source_model": "jewelry.client.metal.receipt",
                "source_res_id": self.id,
                "source_ref": self.name,
                "receipt_id": self.id,
            })
        self.env["jewelry.client.metal.transaction"].create(vals_list)

    def action_post(self):
        for receipt in self:
            if receipt.state != "draft":
                raise UserError(_("Only draft receipts can be confirmed."))
            receipt._validate()
            if receipt.operation_type in ("deposit_metal", "credit_return"):
                receipt._create_metal_document()
            receipt._create_transactions()
            receipt.state = "posted"

    def action_cancel(self):
        for receipt in self:
            if receipt.state == "cancelled":
                raise UserError(_("Receipt is already cancelled."))
            receipt.transaction_ids.filtered(
                lambda t: t.state == "posted"
            ).action_cancel()
            if receipt.metal_document_id and receipt.metal_document_id.state == "posted":
                receipt.metal_document_id.action_cancel()
            receipt.state = "cancelled"

    def action_reset_to_draft(self):
        for receipt in self:
            if receipt.state != "cancelled":
                raise UserError(_("Only cancelled receipts can be reset to draft."))
            receipt.state = "draft"

    def action_view_transactions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Transactions",
            "res_model": "jewelry.client.metal.transaction",
            "view_mode": "tree,form",
            "domain": [("receipt_id", "=", self.id)],
        }

    def action_view_metal_document(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Metal Document",
            "res_model": "jewelry.metal.document",
            "view_mode": "form",
            "res_id": self.metal_document_id.id,
        }


class ClientMetalReceiptLine(models.Model):
    _name = "jewelry.client.metal.receipt.line"
    _description = "Client Metal Receipt Line"

    receipt_id = fields.Many2one(
        "jewelry.client.metal.receipt",
        string="Receipt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    operation_type = fields.Selection(related="receipt_id.operation_type", string="Type")
    currency_id = fields.Many2one(related="receipt_id.currency_id")
    metal_id = fields.Many2one(related="receipt_id.metal_id")

    alloy_id = fields.Many2one(
        "jewelry.metal.alloy",
        string="Alloy",
        domain="[('metal_id', '=', metal_id), ('active', '=', True)]",
    )
    weight_alloy = fields.Float(string="Alloy Weight (g)", digits=(16, 3))
    purity = fields.Float(string="Purity", digits=(16, 6))
    weight_fine = fields.Float(string="Fine Weight (g)", digits=(16, 4))
    rate_datetime = fields.Datetime(
        string="Rate Date",
        default=lambda self: fields.Datetime.now(),
    )
    rate_price_per_gram = fields.Monetary(
        string="Rate (per g fine)",
        currency_field="currency_id",
    )
    money_equivalent = fields.Monetary(
        string="Money Equivalent",
        currency_field="currency_id",
    )

    def _get_metal_rate(self, metal, at_datetime):
        if not metal or not at_datetime:
            return self.env["jewelry.metal.rate"].browse()
        return self.env["jewelry.metal.rate"]._get_latest_rate(metal, at_datetime, self.env.company)

    def _fill_rate(self):
        metal = self.receipt_id.metal_id if self.receipt_id else False
        if not metal:
            return
        if not self.rate_datetime:
            self.rate_datetime = fields.Datetime.now()
        rate = self._get_metal_rate(metal, self.rate_datetime)
        if rate:
            self.rate_price_per_gram = rate.price_per_gram

    @api.onchange("alloy_id")
    def _onchange_alloy_id(self):
        if self.alloy_id:
            self.purity = self.alloy_id.purity
        self._fill_rate()

    @api.onchange("rate_datetime")
    def _onchange_rate_datetime(self):
        self._fill_rate()

    @api.onchange("weight_alloy", "purity")
    def _onchange_weight_fine_from_alloy(self):
        if self.operation_type in ("deposit_metal", "credit_return", "adjustment"):
            self.weight_fine = (self.weight_alloy or 0.0) * (self.purity or 0.0)

    @api.onchange("money_equivalent", "rate_price_per_gram")
    def _onchange_weight_fine_from_cash(self):
        if self.operation_type == "deposit_cash" and self.rate_price_per_gram:
            self.weight_fine = (self.money_equivalent or 0.0) / self.rate_price_per_gram

    @api.onchange("weight_fine")
    def _onchange_weight_alloy_from_fine(self):
        if self.operation_type in ("deposit_metal", "credit_return", "adjustment") and self.purity:
            self.weight_alloy = (self.weight_fine or 0.0) / self.purity
        elif self.operation_type == "deposit_cash" and self.rate_price_per_gram:
            self.money_equivalent = (self.weight_fine or 0.0) * self.rate_price_per_gram
