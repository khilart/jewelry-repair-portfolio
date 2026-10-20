from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Predefined expense categories. They double as expense accounts in the chart
# (picked in the Quick Expense document) and as grouping keys in the P&L dashboard.
# (code, English name, Russian name) — the account name is translatable data, so
# the Russian value is written as a field translation, not via the .po file.
EXPENSE_ACCOUNT_DEFAULTS = [
    # Personnel
    ("EXP100", "Payroll", "Выплата зарплаты"),
    ("EXP110", "Employee Housing", "Аренда жилья сотрудникам"),
    ("EXP120", "Referral Bonus", "% за привлечение клиентов"),
    ("EXP130", "Corporate Events", "Корпоративные мероприятия"),
    # Purchases
    ("EXP200", "Semi-finished Goods", "Покупка полуфабрикатов"),
    ("EXP210", "Stone Purchases", "Покупка камней"),
    ("EXP220", "Metal Account Top-up", "Пополнение аккаунт металл"),
    # Suppliers
    ("EXP300", "Supplier — Casting & Printing", "Оплата поставщикам (литье, печать)"),
    ("EXP310", "Supplier — 3D Printing", "Оплата поставщикам (3-д)"),
    ("EXP320", "Supplier — Gold Plating", "Оплата поставщикам (позолота)"),
    # Operating
    ("EXP400", "Consumables", "Расходные материалы"),
    ("EXP410", "Special Tools", "Специальные инструменты"),
    ("EXP420", "Stationery", "Канцтовары"),
    ("EXP430", "Food", "Продукты"),
    ("EXP440", "Delivery", "Доставка"),
    ("EXP450", "Software", "Программное обеспечение"),
    # Other
    ("EXP500", "Production Investment", "Инвестиции в произв-во"),
    ("EXP510", "Transfer", "Перемещение"),
    ("EXP900", "Other Expenses", "Прочие расходы"),
]


class JewelryExpenseEntry(models.Model):
    _name = "jewelry.expense.entry"
    _description = "Workshop Expense"
    _order = "date desc, id desc"

    name = fields.Char(string="Number", readonly=True, copy=False, default=lambda self: _("New"))
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    account_id = fields.Many2one(
        "account.account",
        string="Category",
        required=True,
        domain="[('account_type', '=', 'expense'), ('code', '=like', 'EXP%')]",
        help="Expense category. Defines the expense account the amount is booked to.",
    )
    amount = fields.Monetary(string="Amount", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Paid From",
        required=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
        default=lambda self: self._default_payment_journal(),
        help="Cash or bank account the money is paid from.",
    )
    partner_id = fields.Many2one("res.partner", string="Vendor / Recipient")
    notes = fields.Char(string="Note")
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        copy=False,
    )
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)

    @api.model
    def _default_payment_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", self.env.company.id)], limit=1
        )

    @api.model
    def _ensure_expense_accounts(self):
        """Create the predefined expense categories for every company if missing.

        account.account records created from static XML get purged when the chart
        of accounts loads, so we create them programmatically and idempotently —
        both at install (post_init_hook) and lazily when the Expenses view opens.
        """
        Account = self.env["account.account"].sudo()
        ru_active = bool(
            self.env["res.lang"].search_count([("code", "=", "ru_RU"), ("active", "=", True)])
        )
        for company in self.env["res.company"].search([]):
            for code, name_en, name_ru in EXPENSE_ACCOUNT_DEFAULTS:
                account = Account.search(
                    [("code", "=", code), ("company_id", "=", company.id)], limit=1
                )
                name_changed = False
                if not account:
                    account = Account.create(
                        {
                            "code": code,
                            "name": name_en,
                            "account_type": "expense",
                            "reconcile": False,
                            "company_id": company.id,
                        }
                    )
                    name_changed = True
                elif account.name != name_en:
                    account.write({"name": name_en})
                    name_changed = True
                # Add or refresh Russian account name.
                if ru_active:
                    current_ru = account.with_context(lang="ru_RU").name
                    if name_changed or not current_ru or current_ru == name_en:
                        account.update_field_translations("name", {"ru_RU": name_ru})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("jewelry.expense.entry") or _("New")
        return super().create(vals_list)

    def unlink(self):
        if any(expense.move_id for expense in self):
            raise UserError(
                _("An expense that already has a journal entry cannot be deleted — "
                  "it would orphan that entry. Use Cancel instead.")
            )
        return super().unlink()

    def _expense_line_vals(self, credit_account):
        """Debit (expense) and credit (cash/bank) line values for the journal entry."""
        self.ensure_one()
        debit_vals = {
            "name": self.notes or self.account_id.name,
            "account_id": self.account_id.id,
            "partner_id": self.partner_id.id,
            "debit": self.amount,
            "credit": 0.0,
        }
        credit_vals = {
            "name": self.notes or self.name,
            "account_id": credit_account.id,
            "partner_id": self.partner_id.id,
            "debit": 0.0,
            "credit": self.amount,
        }
        return debit_vals, credit_vals

    def action_post(self):
        for expense in self:
            if expense.state == "posted":
                continue
            if expense.amount <= 0:
                raise UserError(_("The expense amount must be greater than zero."))
            credit_account = expense.payment_journal_id.default_account_id
            if not credit_account:
                raise UserError(
                    _("Set a default account on the '%s' journal before posting expenses.")
                    % expense.payment_journal_id.name
                )
            debit_vals, credit_vals = expense._expense_line_vals(credit_account)
            move = expense.move_id
            if move and move.state == "draft":
                # Re-posting after Reset to Draft: update the two existing lines in
                # place instead of creating a new move.
                debit_line = move.line_ids.filtered(lambda l: l.balance >= 0)[:1] or move.line_ids[:1]
                credit_line = move.line_ids - debit_line
                move.write(
                    {
                        "journal_id": expense.payment_journal_id.id,
                        "date": expense.date,
                        "ref": expense.name,
                        "line_ids": [
                            (1, debit_line.id, debit_vals),
                            (1, credit_line.id, credit_vals),
                        ],
                    }
                )
            else:
                move = self.env["account.move"].create(
                    {
                        "move_type": "entry",
                        "journal_id": expense.payment_journal_id.id,
                        "date": expense.date,
                        "ref": expense.name,
                        "line_ids": [(0, 0, debit_vals), (0, 0, credit_vals)],
                    }
                )
            move.action_post()
            expense.move_id = move.id
            expense.state = "posted"

    def action_reset_to_draft(self):
        """Reset to Draft to fix a mistake (e.g. wrong amount) before re-posting.

        Available from both Posted and Cancelled — button_draft() supports both
        (Odoo core: "Only posted/cancelled journal entries can be reset to draft").
        Draft moves have zero effect on any balance or report (same exclusion our
        own KPI dashboard applies via parent_state='posted') so the move is just
        unposted and reused on the next Post — nothing is deleted or reversed.
        """
        for expense in self:
            if expense.state not in ("posted", "cancelled"):
                continue
            move = expense.move_id
            if move:
                move.button_draft()
            expense.state = "draft"

    def action_cancel(self):
        """Cancel a posted expense using Odoo's own move cancellation.

        ``button_cancel()`` unposts the move and sets state='cancel' — nothing is
        deleted or reversed, so the audit trail is untouched, and a cancelled move
        is excluded from every balance/report exactly like a draft one.
        """
        for expense in self:
            if expense.state != "posted":
                continue
            move = expense.move_id
            if move:
                move.button_cancel()
            expense.state = "cancelled"

    def action_open_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }
