from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged("post_install", "-at_install")
class TestBilling(TransactionCase):
    """Billing batch selection, confirmation, no-double-billing and invoicing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Billing Client"})
        cls.other_partner = cls.env["res.partner"].create({"name": "Other Billing Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Test Ring"})
        cls.revenue_account = cls.env["account.account"].search([
            ("company_id", "=", cls.env.company.id),
            ("account_type", "=", "income"),
        ], limit=1)
        svc_tmpl = cls.env["product.template"].create({
            "name": "Repair Service",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [(6, 0, [])],
            "property_account_income_id": cls.revenue_account.id,
        })
        cls.service_product = svc_tmpl.product_variant_ids[0]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _make_delivered_order(self, partner=None, price=100.0, qty=1.0):
        partner = partner or self.partner
        order = self.env["jewelry.repair.order"].create({
            "partner_id": partner.id,
            "item_type_id": self.item_type.id,
            "state": "delivered",
            "delivery_date": fields.Date.today(),
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Repair Service",
            "quantity": qty,
            "price_unit": price,
        })
        return order

    def _make_batch(self, partner=None):
        return self.env["jewelry.repair.billing.batch"].create({
            "partner_id": (partner or self.partner).id,
        })

    def _confirmed_batch_with(self, order):
        batch = self._make_batch(order.partner_id)
        batch.action_select_all_orders()
        batch.action_confirm()
        return batch

    # ── candidate selection ──────────────────────────────────────────────────
    def test_candidate_includes_delivered_unbilled(self):
        order = self._make_delivered_order()
        batch = self._make_batch()
        self.assertIn(order, batch._get_candidate_orders())

    def test_candidate_excludes_non_delivered(self):
        order = self._make_delivered_order()
        order.state = "ready"
        batch = self._make_batch()
        self.assertNotIn(order, batch._get_candidate_orders())

    def test_candidate_excludes_other_partner(self):
        order = self._make_delivered_order(partner=self.other_partner)
        batch = self._make_batch(self.partner)
        self.assertNotIn(order, batch._get_candidate_orders())

    # ── confirmation ─────────────────────────────────────────────────────────
    def test_confirm_requires_orders(self):
        batch = self._make_batch()  # no candidates selected
        with self.assertRaises(UserError):
            batch.action_confirm()

    def test_confirm_marks_orders_billed(self):
        order = self._make_delivered_order()
        batch = self._confirmed_batch_with(order)
        self.assertEqual(batch.state, "done")
        self.assertEqual(order.billing_batch_id, batch)
        self.assertTrue(order.billing_date)

    def test_confirm_rejects_order_in_other_batch(self):
        order = self._make_delivered_order()
        self._confirmed_batch_with(order)
        # Force the same order into a second batch and try to confirm it.
        batch2 = self._make_batch()
        batch2.order_ids = [(6, 0, order.ids)]
        with self.assertRaises(UserError):
            batch2.action_confirm()

    # ── no double billing ────────────────────────────────────────────────────
    def test_no_double_billing(self):
        order = self._make_delivered_order()
        self._confirmed_batch_with(order)
        batch2 = self._make_batch()
        self.assertNotIn(order, batch2._get_candidate_orders())

    # ── invoicing ────────────────────────────────────────────────────────────
    def test_create_invoice_requires_done(self):
        order = self._make_delivered_order()
        batch = self._make_batch()
        batch.action_select_all_orders()
        with self.assertRaises(UserError):
            batch.action_create_invoice()

    def test_create_invoice_amount_and_partner(self):
        order = self._make_delivered_order(price=100.0, qty=2.0)
        batch = self._confirmed_batch_with(order)
        batch.action_create_invoice()
        invoice = batch.invoice_id
        self.assertTrue(invoice)
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertAlmostEqual(invoice.amount_total, 200.0, places=2)

    def test_create_invoice_twice_raises(self):
        order = self._make_delivered_order()
        batch = self._confirmed_batch_with(order)
        batch.action_create_invoice()
        with self.assertRaises(UserError):
            batch.action_create_invoice()

    # ── payment status on order ──────────────────────────────────────────────
    def test_payment_status_unbilled(self):
        order = self._make_delivered_order()
        self.assertEqual(order.payment_status, "unbilled")

    def test_payment_status_unpaid_after_billing(self):
        order = self._make_delivered_order()
        batch = self._confirmed_batch_with(order)
        batch.action_create_invoice()
        self.assertEqual(order.payment_status, "unpaid")
