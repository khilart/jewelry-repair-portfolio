from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import date_utils
from odoo.tools.misc import format_date

PRESET_GRANULARITY = {
    "today": "day",
    "this_week": "week",
    "this_month": "month",
    "this_year": "year",
}


class JewelryCashBankStatement(models.TransientModel):
    """Balances and turnover of the cash and bank accounts over a period.

    Turnover is broken down by the counterpart account of each cash line: customer
    payments, every expense category, the rest.
    """
    _name = "jewelry.cash.bank.statement"
    _description = "Cash & Bank Statement"

    period_preset = fields.Selection(
        [
            ("today", "Today"),
            ("this_week", "This Week"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
            ("this_year", "This Year"),
            ("custom", "Custom"),
        ],
        string="Period Preset",
        required=True,
        default="this_month",
    )
    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: self._get_preset_dates("this_month")[0],
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=lambda self: self._get_preset_dates("this_month")[1],
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    account_line_ids = fields.One2many(
        "jewelry.cash.bank.statement.account",
        "statement_id",
        string="Balances",
        readonly=True,
    )
    line_ids = fields.One2many(
        "jewelry.cash.bank.statement.line",
        "statement_id",
        string="Breakdown",
        readonly=True,
    )

    @api.depends("date_from", "date_to")
    def _compute_display_name(self):
        for statement in self:
            statement.display_name = _("Cash & Bank %s", statement._period_label())

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for statement in self:
            if statement.date_from > statement.date_to:
                raise ValidationError(_("The start date must be earlier than or equal to the end date."))

    def _get_preset_dates(self, preset):
        today = fields.Date.context_today(self)
        if preset == "last_month":
            today = date_utils.subtract(date_utils.start_of(today, "month"), days=1)
            preset = "this_month"
        granularity = PRESET_GRANULARITY.get(preset, "day")
        return date_utils.start_of(today, granularity), date_utils.end_of(today, granularity)

    @api.onchange("period_preset")
    def _onchange_period_preset(self):
        if self.period_preset and self.period_preset != "custom":
            self.date_from, self.date_to = self._get_preset_dates(self.period_preset)

    def _period_label(self):
        self.ensure_one()
        if not (self.date_from and self.date_to):
            return ""
        return "%s — %s" % (format_date(self.env, self.date_from), format_date(self.env, self.date_to))

    @api.model
    def action_open_statement(self):
        """Menu entry: the statement for the current month, already built."""
        statement = self.create({})
        statement.action_build_statement()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cash & Bank Statement"),
            "res_model": self._name,
            "res_id": statement.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_build_statement(self):
        self.ensure_one()
        self.account_line_ids.unlink()
        self.line_ids.unlink()

        MoveLine = self.env["account.move.line"]
        accounts = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("account_type", "=", "asset_cash"),
        ])
        posted = [("account_id", "in", accounts.ids), ("parent_state", "=", "posted")]
        opening = dict(MoveLine._read_group(
            posted + [("date", "<", self.date_from)],
            groupby=["account_id"],
            aggregates=["balance:sum"],
        ))
        period_lines = MoveLine.search(
            posted + [("date", ">=", self.date_from), ("date", "<=", self.date_to)],
        )

        by_account = defaultdict(lambda: MoveLine)
        by_counterpart = defaultdict(lambda: MoveLine)
        for line in period_lines:
            by_account[line.account_id] |= line
            by_counterpart[line.account_id, line.counterpart_account_id] |= line

        account_vals = []
        for account in accounts:
            lines = by_account[account]
            opening_balance = opening.get(account, 0.0)
            if not lines and self.currency_id.is_zero(opening_balance):
                continue
            inflow = sum(lines.mapped("debit"))
            outflow = sum(lines.mapped("credit"))
            account_vals.append({
                "statement_id": self.id,
                "account_id": account.id,
                "opening_balance": opening_balance,
                "inflow": inflow,
                "outflow": outflow,
                "closing_balance": opening_balance + inflow - outflow,
            })
        self.env["jewelry.cash.bank.statement.account"].create(account_vals)

        self.env["jewelry.cash.bank.statement.line"].create([
            {
                "statement_id": self.id,
                "account_id": account.id,
                "counterpart_account_id": counterpart.id,
                "name": self._counterpart_label(counterpart),
                "inflow": sum(lines.mapped("debit")),
                "outflow": sum(lines.mapped("credit")),
                "entry_count": len(lines),
                "move_line_ids": [Command.set(lines.ids)],
            }
            for (account, counterpart), lines in sorted(
                by_counterpart.items(),
                key=lambda item: (item[0][0].code, item[0][1].code or ""),
            )
        ])
        return False

    @api.model
    def _counterpart_label(self, account):
        # A receivable or payable account stands for all customers or vendors at once;
        # its own name ("Trade receivables, no separate ...") says nothing to the user.
        if account.account_type == "asset_receivable":
            return _("Customer payments")
        if account.account_type == "liability_payable":
            return _("Vendor payments")
        return account.display_name or _("Other")

    def action_print_statement(self):
        self.ensure_one()
        return self.env.ref("jewelry_repair_billing.action_report_cash_bank_statement").report_action(self)


class JewelryCashBankStatementAccount(models.TransientModel):
    _name = "jewelry.cash.bank.statement.account"
    _description = "Cash & Bank Statement Balance"
    _order = "account_id"

    statement_id = fields.Many2one("jewelry.cash.bank.statement", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="statement_id.currency_id")
    account_id = fields.Many2one("account.account", string="Account", readonly=True)
    opening_balance = fields.Monetary(string="Opening", currency_field="currency_id", readonly=True)
    inflow = fields.Monetary(string="In", currency_field="currency_id", readonly=True)
    outflow = fields.Monetary(string="Out", currency_field="currency_id", readonly=True)
    closing_balance = fields.Monetary(string="Closing", currency_field="currency_id", readonly=True)

    def action_view_moves(self):
        self.ensure_one()
        statement = self.statement_id
        return self.env["account.move.line"]._jewelry_cash_movements_action(
            [
                ("account_id", "=", self.account_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", fields.Date.to_string(statement.date_from)),
                ("date", "<=", fields.Date.to_string(statement.date_to)),
            ],
            "%s (%s)" % (self.account_id.display_name, statement._period_label()),
        )


class JewelryCashBankStatementLine(models.TransientModel):
    _name = "jewelry.cash.bank.statement.line"
    _description = "Cash & Bank Statement Breakdown Line"
    _order = "account_id, counterpart_account_id"

    statement_id = fields.Many2one("jewelry.cash.bank.statement", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="statement_id.currency_id")
    account_id = fields.Many2one("account.account", string="Account", readonly=True)
    counterpart_account_id = fields.Many2one("account.account", string="Counterpart", readonly=True)
    name = fields.Char(string="Item", readonly=True)
    inflow = fields.Monetary(string="In", currency_field="currency_id", readonly=True)
    outflow = fields.Monetary(string="Out", currency_field="currency_id", readonly=True)
    entry_count = fields.Integer(string="Entries", readonly=True)
    move_line_ids = fields.Many2many("account.move.line", readonly=True)

    def action_view_moves(self):
        self.ensure_one()
        return self.env["account.move.line"]._jewelry_cash_movements_action(
            [("id", "in", self.move_line_ids.ids)],
            "%s · %s (%s)" % (self.account_id.code, self.name, self.statement_id._period_label()),
        )
