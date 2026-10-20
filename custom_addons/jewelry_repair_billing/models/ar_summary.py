from odoo import _, fields, models
from odoo.exceptions import UserError


class JewelryRepairARSummary(models.Model):
    _name = "jewelry.repair.ar.summary"
    _description = "Accounts Receivable Summary by Customer"
    _auto = False
    _order = "total_outstanding desc"

    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    unbilled_amount = fields.Monetary(
        string="Unbilled", readonly=True, currency_field="currency_id",
        help="Delivered orders not yet included in any billing batch",
    )
    pending_invoice_amount = fields.Monetary(
        string="Pending Invoice", readonly=True, currency_field="currency_id",
        help="Confirmed billing batches without an invoice yet",
    )
    invoiced_unpaid_amount = fields.Monetary(
        string="Invoiced Unpaid", readonly=True, currency_field="currency_id",
        help="Posted invoices with outstanding balance",
    )
    advance_amount = fields.Monetary(
        string="Advance (Credit)", readonly=True, currency_field="currency_id",
        help="Unreconciled customer prepayments and credit notes available for future invoices",
    )
    total_outstanding = fields.Monetary(
        string="Total Outstanding", readonly=True, currency_field="currency_id",
    )

    def action_open_statement(self):
        """Open the outstanding items of this customer, ready to be printed."""
        self.ensure_one()
        Statement = self.env["jewelry.repair.ar.statement"]
        line_vals = Statement._prepare_lines(self.partner_id)
        if not line_vals:
            raise UserError(_("No outstanding items found for this customer."))
        statement = Statement.create({
            "partner_id": self.partner_id.id,
            "line_ids": [(0, 0, vals) for vals in line_vals],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Statement"),
            "res_model": "jewelry.repair.ar.statement",
            "res_id": statement.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, dialog_size="extra-large"),
        }

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS jewelry_repair_ar_summary")
        self.env.cr.execute("""
            CREATE VIEW jewelry_repair_ar_summary AS (
                SELECT
                    p.id AS id,
                    p.id AS partner_id,
                    comp_cur.id AS currency_id,
                    COALESCE(unbilled.amount, 0) AS unbilled_amount,
                    COALESCE(no_inv.amount, 0) AS pending_invoice_amount,
                    COALESCE(inv.residual, 0) AS invoiced_unpaid_amount,
                    COALESCE(adv.credit, 0) AS advance_amount,
                    COALESCE(unbilled.amount, 0)
                        + COALESCE(no_inv.amount, 0)
                        + COALESCE(inv.residual, 0) AS total_outstanding
                FROM res_partner p
                CROSS JOIN (
                    SELECT c.id
                    FROM res_company rc
                    JOIN res_currency c ON c.id = rc.currency_id
                    WHERE rc.id = 1
                ) comp_cur
                LEFT JOIN (
                    SELECT partner_id, SUM(amount_total) AS amount
                    FROM jewelry_repair_order
                    WHERE state = 'delivered' AND billing_batch_id IS NULL
                    GROUP BY partner_id
                ) unbilled ON unbilled.partner_id = p.id
                LEFT JOIN (
                    SELECT b.partner_id, SUM(o.amount_total) AS amount
                    FROM jewelry_repair_billing_batch b
                    JOIN jewelry_repair_billing_batch_order_rel rel ON rel.batch_id = b.id
                    JOIN jewelry_repair_order o ON o.id = rel.order_id
                    WHERE b.state = 'done'
                      AND (b.invoice_id IS NULL
                           OR (SELECT state FROM account_move WHERE id = b.invoice_id) != 'posted')
                    GROUP BY b.partner_id
                ) no_inv ON no_inv.partner_id = p.id
                LEFT JOIN (
                    SELECT partner_id, SUM(amount_residual) AS residual
                    FROM account_move
                    WHERE move_type = 'out_invoice'
                      AND state = 'posted'
                      AND payment_state NOT IN ('paid', 'reversed')
                    GROUP BY partner_id
                ) inv ON inv.partner_id = p.id
                LEFT JOIN (
                    SELECT aml.partner_id, SUM(-aml.amount_residual) AS credit
                    FROM account_move_line aml
                    JOIN account_account aa ON aa.id = aml.account_id
                    WHERE aa.account_type = 'asset_receivable'
                      AND aml.amount_residual < 0
                      AND aml.parent_state = 'posted'
                    GROUP BY aml.partner_id
                ) adv ON adv.partner_id = p.id
                WHERE
                    COALESCE(unbilled.amount, 0) > 0
                    OR COALESCE(no_inv.amount, 0) > 0
                    OR COALESCE(inv.residual, 0) > 0
                    OR COALESCE(adv.credit, 0) > 0
            )
        """)
