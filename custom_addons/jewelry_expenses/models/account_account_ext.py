import re

from odoo import _, api, models
from odoo.exceptions import UserError

EXPENSE_CATEGORY_CODE_RE = re.compile(r"^EXP\d+$")


class AccountAccount(models.Model):
    _inherit = "account.account"

    def _check_expense_category_code(self, code):
        if code and not EXPENSE_CATEGORY_CODE_RE.match(code):
            raise UserError(_("Expense category code must look like EXPxxx (e.g. EXP520)."))

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("expense_category_form"):
            for vals in vals_list:
                self._check_expense_category_code(vals.get("code"))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("expense_category_form") and "code" in vals:
            self._check_expense_category_code(vals["code"])
        return super().write(vals)
