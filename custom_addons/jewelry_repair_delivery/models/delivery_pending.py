from odoo import api, fields, models


class JewelryRepairDeliveryPending(models.Model):
    _name = "jewelry.repair.delivery.pending"
    _description = "Pending Deliveries by Customer"
    _auto = False
    _order = "earliest_deadline asc"

    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    ready_order_count = fields.Integer(string="Ready Orders", readonly=True)
    ready_amount = fields.Monetary(string="Amount", readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    earliest_deadline = fields.Datetime(string="Earliest Deadline", readonly=True)
    is_overdue = fields.Boolean(string="Overdue", compute="_compute_is_overdue")

    @api.depends("earliest_deadline")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = bool(rec.earliest_deadline and rec.earliest_deadline < now)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW jewelry_repair_delivery_pending AS (
                SELECT
                    o.partner_id AS id,
                    o.partner_id,
                    o.currency_id,
                    COUNT(o.id) AS ready_order_count,
                    SUM(o.amount_total) AS ready_amount,
                    MIN(o.deadline_date) AS earliest_deadline
                FROM jewelry_repair_order o
                WHERE o.state = 'ready'
                GROUP BY o.partner_id, o.currency_id
            )
        """)

    def action_create_delivery(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.delivery",
            "view_mode": "form",
            "context": {"default_partner_id": self.partner_id.id},
        }
