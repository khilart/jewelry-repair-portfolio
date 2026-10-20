from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBalanceStatement(TransactionCase):
    """Customer money statement: orders debit, payments credit, running balance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Statement Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Test Ring"})
        cls.revenue_account = cls.env["account.account"].search([
            ("company_id", "=", cls.env.company.id),
            ("account_type", "=", "income"),
        ], limit=1)
        cls.bank_journal = cls.env["account.journal"].search([
            ("company_id", "=", cls.env.company.id),
            ("type", "=", "bank"),
        ], limit=1)
        template = cls.env["product.template"].create({
            "name": "Repair Service",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [(6, 0, [])],
            "property_account_income_id": cls.revenue_account.id,
        })
        cls.service_product = template.product_variant_ids[0]
        cls.today = fields.Date.today()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _delivered_order(self, price, delivery_date=None):
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "state": "delivered",
            "delivery_date": delivery_date or self.today,
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Repair Service",
            "quantity": 1.0,
            "price_unit": price,
        })
        return order

    def _payment(self, amount, date=None, payment_type="inbound"):
        payment = self.env["account.payment"].create({
            "payment_type": payment_type,
            "partner_type": "customer",
            "partner_id": self.partner.id,
            "amount": amount,
            "date": date or self.today,
            "journal_id": self.bank_journal.id,
        })
        payment.action_post()
        return payment

    def _adjustment(self, amount, adjustment_type="correction", date=None, state="posted"):
        return self.env["jewelry.client.balance.adjustment"].create({
            "partner_id": self.partner.id,
            "date": date or self.today,
            "type": adjustment_type,
            "amount": amount,
            "state": state,
        })

    # ── rows and balance ─────────────────────────────────────────────────────
    def test_order_debits_payment_credits(self):
        self._delivered_order(300.0)
        self._payment(120.0)

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual([row["kind"] for row in rows], ["order", "payment"])
        self.assertEqual(rows[0]["debit"], 300.0)
        self.assertEqual(rows[0]["credit"], 0.0)
        self.assertEqual(rows[1]["credit"], 120.0)
        self.assertEqual(rows[1]["debit"], 0.0)
        self.assertEqual(rows[-1]["balance"], 180.0)

    def test_running_balance_follows_dates(self):
        self._delivered_order(100.0, self.today - timedelta(days=10))
        self._payment(250.0, self.today - timedelta(days=5))
        self._delivered_order(400.0, self.today)

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual([row["balance"] for row in rows], [100.0, -150.0, 250.0])

    def test_overpayment_gives_negative_balance(self):
        self._delivered_order(100.0)
        self._payment(150.0)

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual(rows[-1]["balance"], -50.0)

    def test_refund_to_customer_is_a_debit(self):
        self._delivered_order(100.0)
        self._payment(100.0)
        self._payment(30.0, payment_type="outbound")

        rows = self.partner._jewelry_balance_statement()

        refund_row = rows[-1]
        self.assertEqual(refund_row["debit"], 30.0)
        self.assertEqual(refund_row["balance"], 30.0)

    def test_order_not_delivered_is_absent(self):
        self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
        })

        self.assertFalse(self.partner._jewelry_balance_statement())

    # ── invoices outside the order contour ───────────────────────────────────
    def _standalone_invoice(self, amount, move_type="out_invoice"):
        invoice = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": self.partner.id,
            "invoice_date": self.today,
            "invoice_line_ids": [(0, 0, {
                "name": "Delivery",
                "quantity": 1.0,
                "price_unit": amount,
                "tax_ids": [(6, 0, [])],
                "account_id": self.revenue_account.id,
            })],
        })
        invoice.action_post()
        return invoice

    def test_invoice_outside_billing_is_a_debit(self):
        self._delivered_order(100.0)
        self._standalone_invoice(40.0)

        rows = self.partner._jewelry_balance_statement()

        invoice_row = [row for row in rows if row["kind"] == "invoice"]
        self.assertEqual(len(invoice_row), 1)
        self.assertEqual(invoice_row[0]["debit"], 40.0)
        self.assertEqual(invoice_row[0]["label"], "Delivery")
        self.assertEqual(rows[-1]["balance"], 140.0)

    def test_credit_note_outside_billing_is_a_credit(self):
        self._standalone_invoice(40.0)
        self._standalone_invoice(15.0, move_type="out_refund")

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual(rows[-1]["balance"], 25.0)

    def test_batch_invoice_is_not_counted_twice(self):
        order = self._delivered_order(100.0)
        batch = self.env["jewelry.repair.billing.batch"].create({
            "partner_id": self.partner.id,
        })
        batch.action_select_all_orders()
        batch.action_confirm()
        batch.action_create_invoice()
        batch.invoice_id.action_post()

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual([row["kind"] for row in rows], ["order"])
        self.assertEqual(rows[0]["res_id"], order.id)
        self.assertEqual(rows[-1]["balance"], 100.0)

    # ── opening balance ──────────────────────────────────────────────────────
    def test_opening_balance_starts_the_statement(self):
        self._delivered_order(500.0, self.today - timedelta(days=30))
        self._payment(200.0, self.today - timedelta(days=20))
        self._adjustment(300.0, "opening", self.today - timedelta(days=10))
        self._delivered_order(100.0, self.today)

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual([row["kind"] for row in rows], ["opening", "order"])
        self.assertEqual(rows[0]["debit"], 300.0)
        self.assertEqual(rows[-1]["balance"], 400.0)

    def test_without_opening_the_whole_history_is_listed(self):
        self._delivered_order(500.0, self.today - timedelta(days=30))
        self._delivered_order(100.0, self.today)

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["balance"], 600.0)

    def test_second_opening_balance_is_rejected(self):
        self._adjustment(300.0, "opening")

        with self.assertRaises(ValidationError):
            self._adjustment(100.0, "opening")

    def test_cancelled_opening_frees_the_slot(self):
        first = self._adjustment(300.0, "opening")
        first.state = "cancelled"

        second = self._adjustment(100.0, "opening")

        rows = self.partner._jewelry_balance_statement()
        self.assertEqual(rows[0]["res_id"], second.id)

    # ── adjustments ──────────────────────────────────────────────────────────
    def test_negative_adjustment_credits_the_balance(self):
        self._delivered_order(100.0)
        self._adjustment(-40.0, "write_off")

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual(rows[-1]["credit"], 40.0)
        self.assertEqual(rows[-1]["balance"], 60.0)

    def test_cancelled_adjustment_is_ignored(self):
        self._delivered_order(100.0)
        self._adjustment(-40.0, "write_off", state="cancelled")

        rows = self.partner._jewelry_balance_statement()

        self.assertEqual([row["kind"] for row in rows], ["order"])
        self.assertEqual(rows[-1]["balance"], 100.0)
