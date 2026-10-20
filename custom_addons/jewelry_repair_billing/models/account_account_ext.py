from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    current_debit = fields.Float(compute="_compute_current_debit_credit")
    current_credit = fields.Float(compute="_compute_current_debit_credit")

    def _compute_current_debit_credit(self):
        data = {
            account.id: (debit, credit)
            for account, debit, credit in self.env["account.move.line"]._read_group(
                domain=[("account_id", "in", self.ids), ("parent_state", "=", "posted")],
                groupby=["account_id"],
                aggregates=["debit:sum", "credit:sum"],
            )
        }
        for record in self:
            debit, credit = data.get(record.id, (0.0, 0.0))
            record.current_debit = debit
            record.current_credit = credit

    def action_open_cash_movements(self):
        self.ensure_one()
        return self.env["account.move.line"]._jewelry_cash_movements_action(
            [("account_id", "=", self.id), ("parent_state", "=", "posted")],
            self.display_name,
        )
