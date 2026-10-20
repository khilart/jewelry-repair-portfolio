"""
Tests for rolling back the billing batch and the invoice when a delivered order
is unlocked for editing.

Scenarios:
  1. Posted invoice — cancelled, never deleted (the audit trail keeps it)
  2. Draft invoice that was never posted — deleted outright
  3. The order stays delivered and keeps its place in the batch selection
  4. The batch is flagged as waiting for a rebuild until it is confirmed again
  5. A manager without accounting rights can still run the rollback
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAmendmentRollback(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Rollback Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Rollback Ring"})
        revenue = cls.env["account.account"].search([
            ("company_id", "=", cls.env.company.id),
            ("account_type", "=", "income"),
        ], limit=1)
        template = cls.env["product.template"].create({
            "name": "Rollback Service",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [(6, 0, [])],
            "repair_service_ok": True,
            "property_account_income_id": revenue.id,
        })
        cls.service_product = template.product_variant_ids[0]
        cls.manager = cls.env["res.users"].create({
            "name": "Rollback Manager",
            "login": "test_rollback_manager",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("jewelry_repair_base.group_jewelry_repair_manager").id,
            ])],
        })

    def _delivered_order(self, price=100.0):
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "state": "delivered",
            "delivery_date": fields.Date.today(),
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Rollback Service",
            "quantity": 1.0,
            "price_unit": price,
        })
        return order

    def _billed_order(self, with_invoice=True, post_invoice=True):
        order = self._delivered_order()
        batch = self.env["jewelry.repair.billing.batch"].create({"partner_id": self.partner.id})
        batch.action_select_all_orders()
        batch.action_confirm()
        if with_invoice:
            batch.action_create_invoice()
            if post_invoice:
                batch.invoice_id.action_post()
        return order, batch

    # ── rollback ─────────────────────────────────────────────────────────────
    def test_posted_invoice_is_cancelled_not_deleted(self):
        order, batch = self._billed_order()
        invoice = batch.invoice_id
        self.assertEqual(invoice.state, "posted")

        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertTrue(invoice.exists(), "a posted invoice must survive for the audit trail")
        self.assertEqual(invoice.state, "cancel")

    def test_never_posted_invoice_is_deleted(self):
        order, batch = self._billed_order(post_invoice=False)
        invoice = batch.invoice_id
        self.assertEqual(invoice.state, "draft")
        self.assertFalse(invoice.posted_before)

        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertFalse(invoice.exists(), "a draft that was never posted leaves no trace")

    def test_batch_goes_back_to_draft_and_keeps_the_selection(self):
        order, batch = self._billed_order()
        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertEqual(batch.state, "draft")
        self.assertIn(order, batch.order_ids)
        self.assertTrue(batch.line_ids.filtered(lambda line: line.order_id == order).selected)
        self.assertFalse(order.billing_batch_id)

    def test_order_stays_delivered_and_becomes_editable(self):
        order, batch = self._billed_order()
        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertEqual(order.state, "delivered")
        self.assertTrue(order.amendment_open)
        order.with_user(self.manager).service_line_ids.write({"price_unit": 150.0})
        self.assertEqual(order.amount_total, 150.0)

    def test_batch_is_flagged_as_waiting_for_rebuild(self):
        order, batch = self._billed_order()
        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertTrue(batch.rebuild_pending)
        self.assertIn(order, batch.amendment_order_ids)
        self.assertEqual(order.amendment_billing_batch_id, batch)
        self.assertIn(batch, self.env["jewelry.repair.billing.batch"].search(
            [("rebuild_pending", "=", True)]))

    def test_cancelled_documents_are_named_in_the_chatter(self):
        order, batch = self._billed_order()
        invoice = batch.invoice_id
        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertIn(invoice.name, order.message_ids[:1].body)
        self.assertIn(order.name, batch.message_ids[:1].body)
        self.assertIn(order.name, invoice.message_ids[:1].body)

    # ── rebuild ──────────────────────────────────────────────────────────────
    def test_rebuild_clears_the_flags_and_bills_the_new_amount(self):
        order, batch = self._billed_order()
        order.with_user(self.manager)._open_amendment("wrong price")
        order.with_user(self.manager).service_line_ids.write({"price_unit": 150.0})

        batch.action_confirm()
        action = batch.action_create_invoice()

        self.assertEqual(action["res_model"], "account.move",
                         "the new invoice is opened so the payment can be matched")
        self.assertEqual(batch.invoice_id.amount_total, 150.0)
        self.assertFalse(batch.rebuild_pending)
        self.assertFalse(order.amendment_open)
        self.assertFalse(order.amendment_billing_batch_id)
        self.assertEqual(order.billing_batch_id, batch)
