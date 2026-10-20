from odoo import api, fields, models


class JewelryRepairKpiExpenseLine(models.TransientModel):
    _name = "jewelry.repair.kpi.expense.line"
    _description = "KPI Dashboard Expense Line"
    _order = "amount desc"

    dashboard_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    dashboard_prev_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    account_name = fields.Char(string="Category", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")

    @api.depends("dashboard_id", "dashboard_prev_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (rec.dashboard_id or rec.dashboard_prev_id).currency_id


class JewelryRepairKpiDashboard(models.TransientModel):
    _inherit = "jewelry.repair.kpi.dashboard"

    expense_total_current = fields.Monetary(
        string="Total Expenses This Month", currency_field="currency_id", readonly=True
    )
    expense_total_prev = fields.Monetary(
        string="Total Expenses Last Month", currency_field="currency_id", readonly=True
    )
    profit_current = fields.Monetary(
        string="Net Profit This Month", currency_field="currency_id", readonly=True
    )
    profit_prev = fields.Monetary(
        string="Net Profit Last Month", currency_field="currency_id", readonly=True
    )
    expense_month_ids = fields.One2many(
        "jewelry.repair.kpi.expense.line", "dashboard_id", string="Expenses This Month"
    )
    expense_prev_ids = fields.One2many(
        "jewelry.repair.kpi.expense.line", "dashboard_prev_id", string="Expenses Last Month"
    )

    def _get_expense_data(self, date_from, date_to):
        """Aggregate posted expense move lines (quick expenses + vendor bills) by account."""
        domain = [
            ("account_id.account_type", "=", "expense"),
            ("parent_state", "=", "posted"),
            ("date", ">=", str(date_from)),
            ("company_id", "=", self.env.company.id),
        ]
        if date_to:
            domain.append(("date", "<", str(date_to)))
        groups = self.env["account.move.line"].read_group(
            domain, ["balance:sum"], ["account_id"]
        )
        rows = []
        for group in groups:
            amount = group["balance"] or 0.0
            if self.env.company.currency_id.is_zero(amount):
                continue
            account = self.env["account.account"].browse(group["account_id"][0])
            rows.append({"account_name": account.name, "amount": amount})
        return sorted(rows, key=lambda r: -r["amount"])

    @api.model
    def action_open_dashboard(self):
        action = super().action_open_dashboard()
        record = self.browse(action.get("res_id"))
        if not record.exists():
            return action

        current = self._get_expense_data(record.date_from, None)
        prev = self._get_expense_data(record.date_prev_from, record.date_prev_to)

        ExpenseLine = self.env["jewelry.repair.kpi.expense.line"].sudo()
        for row in current:
            ExpenseLine.create({"dashboard_id": record.id, **row})
        for row in prev:
            ExpenseLine.create({"dashboard_prev_id": record.id, **row})

        expense_total_current = sum(row["amount"] for row in current)
        expense_total_prev = sum(row["amount"] for row in prev)
        record.sudo().write(
            {
                "expense_total_current": expense_total_current,
                "expense_total_prev": expense_total_prev,
                "profit_current": record.revenue_month - expense_total_current,
                "profit_prev": record.revenue_prev_month - expense_total_prev,
            }
        )
        return action
