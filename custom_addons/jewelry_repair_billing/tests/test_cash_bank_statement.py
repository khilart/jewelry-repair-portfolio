from datetime import date

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCashBankStatement(TransactionCase):
    """Cash & Bank statement: balances, turnover by counterpart, running balance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.cash_account = cls.env["account.account"].create({
            "code": "JCB101",
            "name": "Test Cash",
            "account_type": "asset_cash",
        })
        cls.expense_account = cls.env["account.account"].create({
            "code": "JCBEXP1",
            "name": "Test Payroll",
            "account_type": "expense",
        })
        cls.receivable_account = cls.env["account.account"].search([
            ("company_id", "=", company.id),
            ("account_type", "=", "asset_receivable"),
        ], limit=1)
        cls.journal = cls.env["account.journal"].search([
            ("company_id", "=", company.id),
            ("type", "=", "general"),
        ], limit=1)
        cls.partner = cls.env["res.partner"].create({"name": "Cash Statement Client"})
        # Next year keeps the entries clear of lock dates and of the existing data.
        year = fields.Date.today().year + 1
        cls.date_from = date(year, 3, 1)
        cls.date_to = date(year, 3, 31)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _entry(self, entry_date, amount, counterpart, post=True):
        """Journal entry on the test cash account; a positive amount is money in."""
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal.id,
            "date": entry_date,
            "line_ids": [
                Command.create({
                    "account_id": self.cash_account.id,
                    "partner_id": self.partner.id,
                    "name": "Cash",
                    "debit": max(amount, 0.0),
                    "credit": max(-amount, 0.0),
                }),
                Command.create({
                    "account_id": counterpart.id,
                    "partner_id": self.partner.id,
                    "name": "Counterpart",
                    "debit": max(-amount, 0.0),
                    "credit": max(amount, 0.0),
                }),
            ],
        })
        if post:
            move.action_post()
        return move

    def _statement(self):
        statement = self.env["jewelry.cash.bank.statement"].create({
            "period_preset": "custom",
            "date_from": self.date_from,
            "date_to": self.date_to,
        })
        statement.action_build_statement()
        return statement

    def _account_line(self, statement):
        return statement.account_line_ids.filtered(lambda l: l.account_id == self.cash_account)

    def _breakdown(self, statement, counterpart):
        return statement.line_ids.filtered(
            lambda l: l.account_id == self.cash_account and l.counterpart_account_id == counterpart
        )

    # ── tests ────────────────────────────────────────────────────────────────
    def test_balances_and_turnover(self):
        self._entry(date(self.date_from.year, 2, 15), 100.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 5), 50.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 10), -30.0, self.expense_account)
        self._entry(date(self.date_from.year, 4, 2), -999.0, self.expense_account)

        statement = self._statement()
        line = self._account_line(statement)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.opening_balance, 100.0)
        self.assertAlmostEqual(line.inflow, 50.0)
        self.assertAlmostEqual(line.outflow, 30.0)
        self.assertAlmostEqual(line.closing_balance, 120.0)

        statement.action_build_statement()
        self.assertEqual(len(self._account_line(statement)), 1, "a rebuild replaces the lines")

    def test_only_posted_entries_count(self):
        self._entry(date(self.date_from.year, 3, 5), 50.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 6), -20.0, self.expense_account, post=False)
        self._entry(date(self.date_from.year, 3, 7), -40.0, self.expense_account).button_cancel()

        line = self._account_line(self._statement())
        self.assertAlmostEqual(line.inflow, 50.0)
        self.assertAlmostEqual(line.outflow, 0.0)
        self.assertAlmostEqual(line.closing_balance, 50.0)

    def test_account_without_balance_or_movements_is_skipped(self):
        self.assertFalse(self._account_line(self._statement()))

    def test_breakdown_by_counterpart(self):
        self._entry(date(self.date_from.year, 3, 5), 50.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 6), 25.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 10), -30.0, self.expense_account)
        # A reversed expense comes back as money in on the same category.
        self._entry(date(self.date_from.year, 3, 11), 10.0, self.expense_account)

        statement = self._statement()
        customers = self._breakdown(statement, self.receivable_account)
        self.assertEqual(customers.name, "Customer payments")
        self.assertAlmostEqual(customers.inflow, 75.0)
        self.assertEqual(customers.entry_count, 2)

        payroll = self._breakdown(statement, self.expense_account)
        self.assertEqual(payroll.name, self.expense_account.display_name)
        self.assertAlmostEqual(payroll.inflow, 10.0)
        self.assertAlmostEqual(payroll.outflow, 30.0)

        action = payroll.action_view_moves()
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(lines, payroll.move_line_ids)
        self.assertEqual(lines.account_id, self.cash_account)
        self.assertEqual(len(lines), 2)

    def test_counterpart_is_largest_other_line(self):
        move = self._entry(date(self.date_from.year, 3, 5), -30.0, self.expense_account)
        cash_line = move.line_ids.filtered(lambda l: l.account_id == self.cash_account)
        self.assertEqual(cash_line.counterpart_account_id, self.expense_account)

    def test_running_balance_ignores_list_filter(self):
        self._entry(date(self.date_from.year, 2, 15), 100.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 5), 50.0, self.receivable_account)
        self._entry(date(self.date_from.year, 3, 10), -30.0, self.expense_account)

        lines = self.env["account.move.line"].search([
            ("account_id", "=", self.cash_account.id),
            ("date", ">=", self.date_from),
        ], order="date, id")
        self.assertEqual(
            lines.mapped("running_balance"), [150.0, 120.0],
            "the opening balance before the filtered period is carried in",
        )

    def test_wrong_period_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["jewelry.cash.bank.statement"].create({
                "period_preset": "custom",
                "date_from": self.date_to,
                "date_to": self.date_from,
            })

    def test_last_month_preset(self):
        statement = self.env["jewelry.cash.bank.statement"].new({})
        date_from, date_to = statement._get_preset_dates("last_month")
        today = fields.Date.context_today(statement)
        self.assertEqual(date_from.day, 1)
        self.assertEqual((date_from.year, date_from.month), (date_to.year, date_to.month))
        self.assertEqual((today.replace(day=1) - date_to).days, 1, "ends the day before this month")
