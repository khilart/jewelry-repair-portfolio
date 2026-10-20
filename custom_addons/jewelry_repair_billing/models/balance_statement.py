from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Rows sharing a date are shown in this order, so that a payment always follows the
# orders of the same day and the opening balance stays on top.
KIND_SEQUENCE = {"opening": 0, "order": 1, "invoice": 2, "payment": 3, "adjustment": 4}


class JewelryClientBalanceAdjustment(models.Model):
    """Manual row of the customer money statement.

    Covers the balance carried over from before the system was introduced
    (``opening``) as well as what shows up later: a written-off debt, a discount
    granted after the fact, a correction of a mistake.
    """
    _name = "jewelry.client.balance.adjustment"
    _description = "Client Balance Adjustment"
    _order = "date desc, id desc"

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        index=True,
        ondelete="restrict",
    )
    date = fields.Date(required=True, default=fields.Date.context_today)
    type = fields.Selection(
        [
            ("opening", "Opening Balance"),
            ("write_off", "Write-off"),
            ("correction", "Correction"),
        ],
        string="Type",
        required=True,
        default="correction",
    )
    amount = fields.Monetary(
        required=True,
        currency_field="currency_id",
        help="Positive increases what the customer owes, negative decreases it.",
    )
    label = fields.Char(string="Description")
    state = fields.Selection(
        [("posted", "Posted"), ("cancelled", "Cancelled")],
        default="posted",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.constrains("partner_id", "type", "state")
    def _check_single_opening(self):
        for adjustment in self:
            if adjustment.type != "opening" or adjustment.state != "posted":
                continue
            if self.search_count([
                ("partner_id", "=", adjustment.partner_id.id),
                ("type", "=", "opening"),
                ("state", "=", "posted"),
                ("id", "!=", adjustment.id),
            ]):
                raise ValidationError(_(
                    "%s already has an opening balance. Cancel the existing one before "
                    "entering another.",
                    adjustment.partner_id.display_name,
                ))


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _jewelry_statement_settles_with_metal(self):
        """True when the customer pays part of the bill with their own metal.

        The amount such a customer has to settle in money is only known once the
        billing batch is confirmed, so those orders join the statement later than
        the rest — see _jewelry_balance_statement().
        """
        self.ensure_one()
        if "jewelry.client.metal.account" not in self.env:
            return False
        return bool(self.env["jewelry.client.metal.account"].sudo().search_count([
            ("partner_id", "=", self.id),
            ("active", "=", True),
        ]))

    def _jewelry_order_money_amount(self, order):
        """Amount of an order the customer has to settle in money.

        Once the batch is confirmed, the client metal offset is already deducted
        from the billed amount, and that is what has to be paid in cash.
        """
        self.ensure_one()
        if order.billing_batch_id.state == "done":
            billing_line = order.billing_batch_id.line_ids.filtered(
                lambda bl: bl.order_id == order
            )[:1]
            if billing_line and "effective_amount_total" in billing_line._fields:
                return billing_line.effective_amount_total
        return order.amount_total

    def _jewelry_balance_statement(self):
        """Ledger rows of the customer money statement, oldest first.

        A delivered order is a debit, a payment received is a credit, and each row
        carries the balance after it. Invoices are deliberately not rows of their
        own: the debit side is built from orders, and an invoice is only the
        document those orders are presented with. For the same reason credit notes
        are left out — in this contour they reverse an invoice rather than move
        money, and would lower the debt a second time.
        """
        self.ensure_one()
        Adjustment = self.env["jewelry.client.balance.adjustment"].sudo()

        opening = Adjustment.search([
            ("partner_id", "=", self.id),
            ("type", "=", "opening"),
            ("state", "=", "posted"),
        ], limit=1)
        # The opening balance already contains everything that happened before it.
        date_from = opening.date if opening else None

        rows = []
        if opening:
            rows.append(self._jewelry_statement_row(
                opening.date, "opening", opening.id,
                _("Opening balance"), opening.label or "", opening.amount,
            ))

        order_domain = [
            ("partner_id", "=", self.id),
            ("state", "=", "delivered"),
        ]
        if date_from:
            order_domain.append(("delivery_date", ">=", date_from))
        if self._jewelry_statement_settles_with_metal():
            order_domain.append(("billing_batch_id.state", "=", "done"))
        orders = self.env["jewelry.repair.order"].sudo().search(order_domain)
        for order in orders:
            rows.append(self._jewelry_statement_row(
                order.delivery_date or fields.Date.context_today(self), "order", order.id,
                order.item_type_id.name or _("Order"), order.name,
                self._jewelry_order_money_amount(order),
                order=order,
            ))

        rows.extend(self._jewelry_statement_invoice_rows(date_from))

        payment_domain = [
            ("partner_id", "=", self.id),
            ("partner_type", "=", "customer"),
            ("state", "=", "posted"),
            ("company_id", "=", self.env.company.id),
        ]
        if date_from:
            payment_domain.append(("date", ">=", date_from))
        payments = self.env["account.payment"].sudo().search(payment_domain)
        for payment in payments:
            # Positive for money received, negative for money returned to the
            # customer, already converted to the company currency.
            received = payment.amount_company_currency_signed
            rows.append(self._jewelry_statement_row(
                payment.date, "payment", payment.id,
                _("Payment") if received > 0 else _("Refund"),
                payment.name or "", -received,
            ))

        adjustment_domain = [
            ("partner_id", "=", self.id),
            ("type", "!=", "opening"),
            ("state", "=", "posted"),
        ]
        if date_from:
            adjustment_domain.append(("date", ">=", date_from))
        type_labels = dict(Adjustment._fields["type"]._description_selection(self.env))
        for adjustment in Adjustment.search(adjustment_domain):
            rows.append(self._jewelry_statement_row(
                adjustment.date, "adjustment", adjustment.id,
                type_labels[adjustment.type],
                adjustment.label or "", adjustment.amount,
            ))

        rows.sort(key=lambda row: (
            row["date"], KIND_SEQUENCE[row["kind"]], row["res_id"],
        ))

        balance = 0.0
        for row in rows:
            balance += row["debit"] - row["credit"]
            row["balance"] = balance

        return rows

    def _jewelry_statement_invoice_rows(self, date_from):
        """Invoices billed outside the order contour — delivery charges and the like.

        Invoices of a billing batch are left out: their orders are already on the
        debit side. What is left is billed to the customer and owed by them, so
        without these rows the statement would understate the debt.
        """
        self.ensure_one()
        batch_invoices = self.env["jewelry.repair.billing.batch"].sudo().search([
            ("partner_id", "=", self.id),
            ("invoice_id", "!=", False),
        ]).mapped("invoice_id")

        domain = [
            ("partner_id", "=", self.id),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("company_id", "=", self.env.company.id),
            ("id", "not in", batch_invoices.ids),
            # A credit note reversing a batch invoice belongs to that same contour.
            ("reversed_entry_id", "not in", batch_invoices.ids),
        ]
        if date_from:
            domain.append(("invoice_date", ">=", date_from))

        rows = []
        for invoice in self.env["account.move"].sudo().search(domain):
            names = list(dict.fromkeys(
                line.name for line in invoice.invoice_line_ids if line.name
            ))
            label = ", ".join(names[:3]) if names else _("Invoice")
            amount = invoice.amount_total
            if invoice.move_type == "out_refund":
                amount = -amount
            rows.append(self._jewelry_statement_row(
                invoice.invoice_date, "invoice", invoice.id,
                label, invoice.name or "", amount,
            ))
        return rows

    def _jewelry_statement_row(self, date, kind, res_id, label, reference, amount, order=None):
        """One statement row; a positive amount is what the customer owes more."""
        return {
            "date": date,
            "kind": kind,
            "res_id": res_id,
            "label": label,
            "reference": reference,
            "debit": amount if amount > 0 else 0.0,
            "credit": -amount if amount < 0 else 0.0,
            "order": order,
        }
