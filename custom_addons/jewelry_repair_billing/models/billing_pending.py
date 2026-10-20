from dateutil.relativedelta import relativedelta

from odoo import fields, models


class JewelryRepairBillingPending(models.Model):
    _name = "jewelry.repair.billing.pending"
    _description = "Pending Billing by Customer"
    _auto = False
    _order = "unbilled_order_count desc"

    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    last_billing_date_to = fields.Date(string="Last Billed To", readonly=True)
    unbilled_order_count = fields.Integer(string="Unbilled Orders", readonly=True)
    unbilled_amount = fields.Monetary(string="Amount to Bill", readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW jewelry_repair_billing_pending AS (
                SELECT
                    o.partner_id AS id,
                    o.partner_id,
                    o.currency_id,
                    COUNT(o.id) AS unbilled_order_count,
                    SUM(o.amount_total) AS unbilled_amount,
                    last_batch.date_to AS last_billing_date_to
                FROM jewelry_repair_order o
                LEFT JOIN (
                    SELECT partner_id, MAX(date_to) AS date_to
                    FROM jewelry_repair_billing_batch
                    WHERE state = 'done'
                    GROUP BY partner_id
                ) last_batch ON last_batch.partner_id = o.partner_id
                WHERE o.state = 'delivered'
                  AND o.billing_batch_id IS NULL
                GROUP BY o.partner_id, o.currency_id, last_batch.date_to
            )
        """)

    def action_create_batch(self):
        self.ensure_one()
        date_from = None
        if self.last_billing_date_to:
            date_from = self.last_billing_date_to + relativedelta(days=1)
        else:
            first_order = self.env["jewelry.repair.order"].search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    ("state", "=", "delivered"),
                    ("billing_batch_id", "=", False),
                    ("delivery_date", "!=", False),
                ],
                order="delivery_date asc",
                limit=1,
            )
            if first_order:
                date_from = first_order.delivery_date

        batch = self.env["jewelry.repair.billing.batch"].search([
            ("partner_id", "=", self.partner_id.id),
            ("state", "=", "draft"),
        ], limit=1)

        if not batch:
            batch = self.env["jewelry.repair.billing.batch"].create({
                "partner_id": self.partner_id.id,
                "date_from": date_from,
                "date_to": fields.Date.today(),
            })
            batch.action_select_all_orders()

        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.billing.batch",
            "view_mode": "form",
            "res_id": batch.id,
        }
