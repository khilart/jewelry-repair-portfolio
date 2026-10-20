from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    counterpart_account_id = fields.Many2one(
        "account.account",
        string="Counterpart",
        compute="_compute_counterpart_account_id",
        help="Account of the largest other line of the same journal entry.",
    )
    running_balance = fields.Monetary(
        string="Balance After",
        compute="_compute_running_balance",
        currency_field="company_currency_id",
        help="Balance of the account after this line, over all posted lines in date "
             "order, whatever filters are applied to the list.",
    )

    def _compute_counterpart_account_id(self):
        for line in self:
            others = line.move_id.line_ids - line
            counterpart = max(others, key=lambda other: abs(other.balance), default=None)
            line.counterpart_account_id = counterpart.account_id if counterpart else False

    def _compute_running_balance(self):
        # The core cumulated_balance sums only the lines matching the list domain, so a
        # list filtered on a month starts from zero and loses the opening balance.
        result = {}
        if self.account_id:
            self.flush_model(["account_id", "date", "balance", "parent_state"])
            self.env.cr.execute("""
                SELECT id, SUM(balance) OVER (PARTITION BY account_id ORDER BY date, id)
                  FROM account_move_line
                 WHERE account_id IN %s
                   AND parent_state = 'posted'
            """, [tuple(self.account_id.ids)])
            result = dict(self.env.cr.fetchall())
        for line in self:
            line.running_balance = result.get(line.id, 0.0)

    @api.model
    def _jewelry_cash_movements_action(self, domain, name):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "account.move.line",
            "view_mode": "tree",
            "views": [(self.env.ref("jewelry_repair_billing.view_jewelry_cash_movement_tree").id, "tree")],
            "domain": domain,
            "context": {"create": False},
        }
