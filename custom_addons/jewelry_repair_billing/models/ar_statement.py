from odoo import _, api, fields, models
from odoo.exceptions import UserError

# English labels used in the printed statement, independent of the user language.
SOURCE_LABELS_EN = {
    "unbilled": "Unbilled",
    "billed": "Billed, not invoiced",
    "invoiced": "Invoiced, unpaid",
}
SOURCE_SEQUENCE = ["unbilled", "billed", "invoiced"]


class JewelryRepairARStatement(models.TransientModel):
    _name = "jewelry.repair.ar.statement"
    _description = "Customer Outstanding Statement"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True)
    date = fields.Date(string="Statement Date", default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        readonly=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    line_ids = fields.One2many(
        "jewelry.repair.ar.statement.line",
        "statement_id",
        string="Outstanding Items",
    )
    amount_gross = fields.Monetary(
        string="Orders Total",
        compute="_compute_amounts",
        currency_field="currency_id",
    )
    amount_payments = fields.Monetary(
        string="Payments Received",
        compute="_compute_amounts",
        currency_field="currency_id",
    )
    amount_due = fields.Monetary(
        string="Total Due",
        compute="_compute_amounts",
        currency_field="currency_id",
    )

    @api.depends("line_ids.selected", "line_ids.amount", "line_ids.payment_applied")
    def _compute_amounts(self):
        for statement in self:
            selected = statement.line_ids.filtered("selected")
            statement.amount_gross = sum(selected.mapped("amount"))
            statement.amount_payments = sum(selected.mapped("payment_applied"))
            statement.amount_due = statement.amount_gross - statement.amount_payments

    @api.model
    def _prepare_lines(self, partner):
        """Build statement line values covering the whole outstanding balance of a customer.

        The three buckets mirror jewelry.repair.ar.summary: delivered orders not yet
        billed, confirmed batches without a posted invoice, and posted invoices with a
        remaining balance.
        """
        vals_list = []

        batches = self.env["jewelry.repair.billing.batch"].search([
            ("partner_id", "=", partner.id),
            ("state", "=", "done"),
        ])
        # jewelry_client_metal_accounts reduces the billed amount by the client metal
        # offset; jewelry.repair.ar.summary uses the same figure, so follow it here.
        batch_lines = {bl.order_id.id: bl for batch in batches for bl in batch.line_ids}

        def billed_amount(order):
            billing_line = batch_lines.get(order.id)
            if billing_line and "effective_amount_total" in billing_line._fields:
                return billing_line.effective_amount_total
            return order.amount_total

        unbilled_orders = self.env["jewelry.repair.order"].search(
            [
                ("partner_id", "=", partner.id),
                ("state", "=", "delivered"),
                ("billing_batch_id", "=", False),
            ],
            order="delivery_date, id",
        )
        for order in unbilled_orders:
            vals_list.append({
                "source": "unbilled",
                "order_id": order.id,
                "amount": order.amount_total,
            })

        for batch in batches:
            if batch.invoice_id and batch.invoice_id.state == "posted":
                continue
            for order in batch.order_ids.sorted(lambda o: (o.delivery_date or fields.Date.today(), o.id)):
                vals_list.append({
                    "source": "billed",
                    "order_id": order.id,
                    "batch_id": batch.id,
                    "reference": batch.name,
                    "amount": billed_amount(order),
                })

        invoices = self.env["account.move"].search([
            ("partner_id", "=", partner.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "not in", ("paid", "reversed")),
        ])
        for invoice in invoices:
            orders = batches.filtered(lambda b: b.invoice_id == invoice).mapped("order_ids")
            orders_total = sum(billed_amount(order) for order in orders)
            if not orders or orders_total <= 0:
                vals_list.append({
                    "source": "invoiced",
                    "invoice_id": invoice.id,
                    "reference": invoice.name,
                    "amount": invoice.amount_residual,
                })
                continue
            # Payments already received against this invoice are spread over its orders,
            # so that deselecting part of them keeps the deduction proportional.
            paid = max(orders_total - invoice.amount_residual, 0.0)
            for order in orders.sorted(lambda o: (o.delivery_date or fields.Date.today(), o.id)):
                amount = billed_amount(order)
                vals_list.append({
                    "source": "invoiced",
                    "order_id": order.id,
                    "invoice_id": invoice.id,
                    "reference": invoice.name,
                    "amount": amount,
                    "payment_applied": paid * amount / orders_total,
                })

        return vals_list

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({"selected": True})
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Statement"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, dialog_size="extra-large"),
        }

    def action_clear_selection(self):
        self.ensure_one()
        self.line_ids.write({"selected": False})
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Statement"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, dialog_size="extra-large"),
        }

    def action_print_statement(self):
        self.ensure_one()
        if not self.line_ids.filtered("selected"):
            raise UserError(_("Select at least one item to print the statement."))
        # The report itself is forced to English through FORCE_ENGLISH_REPORTS.
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_billing.report_jewelry_customer_statement/%s" % self.id,
            "target": "new",
        }

    def _selected_orders(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.selected and l.order_id).mapped("order_id")

    def _get_statement_groups(self):
        """Rows for the printed statement, grouped by outstanding bucket, in English."""
        self.ensure_one()
        groups = []
        for source in SOURCE_SEQUENCE:
            lines = self.line_ids.filtered(lambda l, s=source: l.selected and l.source == s)
            if not lines:
                continue
            groups.append({
                "label": SOURCE_LABELS_EN[source],
                "lines": [{
                    "order_name": line.order_id.name or "",
                    "item": (
                        line.order_id.item_type_id.with_context(lang=False).name
                        or line.order_id.item_type_id.name
                        or ""
                    ) if line.order_id else "",
                    "quantity": line.order_id.quantity if line.order_id else 0,
                    "delivery_date": (
                        line.order_id.delivery_date.strftime("%d %b %Y")
                        if line.order_id and line.order_id.delivery_date else ""
                    ),
                    "reference": line.reference or "",
                    "amount": line.amount,
                } for line in lines],
                "quantity": sum(line.order_id.quantity for line in lines if line.order_id),
                "subtotal": sum(lines.mapped("amount")),
            })
        return groups

    def _get_statement_service_summary(self):
        self.ensure_one()
        return self._selected_orders()._jewelry_service_summary()

    def _get_statement_material_summary(self):
        self.ensure_one()
        return self._selected_orders()._jewelry_material_summary()


class JewelryRepairARStatementLine(models.TransientModel):
    _name = "jewelry.repair.ar.statement.line"
    _description = "Customer Outstanding Statement Line"

    statement_id = fields.Many2one(
        "jewelry.repair.ar.statement",
        string="Statement",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Include", default=True)
    source = fields.Selection(
        [
            ("unbilled", "Unbilled"),
            ("billed", "Billed, not invoiced"),
            ("invoiced", "Invoiced, unpaid"),
        ],
        string="Status",
        required=True,
    )
    reference = fields.Char(string="Document")
    order_id = fields.Many2one("jewelry.repair.order", string="Repair Order")
    batch_id = fields.Many2one("jewelry.repair.billing.batch", string="Billing Batch")
    invoice_id = fields.Many2one("account.move", string="Invoice")
    order_name = fields.Char(related="order_id.name", string="Order No.", readonly=True)
    order_item_type_id = fields.Many2one(related="order_id.item_type_id", string="Item Type", readonly=True)
    order_quantity = fields.Integer(related="order_id.quantity", string="Qty", readonly=True)
    order_delivery_date = fields.Date(related="order_id.delivery_date", string="Delivery Date", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id")
    payment_applied = fields.Monetary(string="Paid", currency_field="currency_id")
    currency_id = fields.Many2one(related="statement_id.currency_id", readonly=True)

    def action_open_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.order",
            "res_id": self.order_id.id,
            "view_mode": "form",
            "target": "new",
        }
