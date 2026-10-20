"""
Tests for correcting a delivered order that has not been billed yet.

The delivery document stores no amounts of its own — its lines only point at orders
and read through to them — so correcting an order must be reflected there without
touching or cancelling the delivery.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAmendmentWithDelivery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({
            "name": "Delivery Amendment Manager",
            "login": "test_delivery_amendment_manager",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("jewelry_repair_base.group_jewelry_repair_manager").id,
            ])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "Delivery Amendment Customer"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Delivery Ring"})
        template = cls.env["product.template"].create({
            "name": "Delivery Amendment Service",
            "type": "service",
            "list_price": 100.0,
            "repair_service_ok": True,
        })
        cls.service_product = template.product_variant_ids[0]

    def _delivered_order_with_document(self, price=100.0):
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Delivery Amendment Service",
            "quantity": 1.0,
            "price_unit": price,
        })
        order.write({"state": "ready", "ready_accepted_by_manager": True})

        delivery = self.env["jewelry.repair.delivery"].create({"partner_id": self.partner.id})
        delivery.line_ids.filtered(lambda line: line.order_id == order).selected = True
        delivery._sync_order_ids_from_selected_lines()
        delivery.action_confirm()
        return order, delivery

    def test_delivery_follows_the_corrected_order(self):
        order, delivery = self._delivered_order_with_document(price=100.0)
        self.assertEqual(delivery.state, "done")
        self.assertEqual(delivery.selected_amount_total, 100.0)

        order = order.with_user(self.manager)
        order._open_amendment("wrong price")
        order.service_line_ids.write({"price_unit": 150.0})

        self.assertEqual(order.amount_total, 150.0)
        self.assertEqual(delivery.selected_amount_total, 150.0,
                         "the delivery reads through to the order and needs no rebuild")
        self.assertEqual(delivery.state, "done", "the delivery must not be cancelled")

    def test_corrected_order_stays_out_of_delivery_candidates(self):
        order, delivery = self._delivered_order_with_document()
        order = order.with_user(self.manager)
        order._open_amendment("wrong price")

        self.assertEqual(order.state, "delivered")
        self.assertEqual(order.delivery_id, delivery)

        new_delivery = self.env["jewelry.repair.delivery"].create({"partner_id": self.partner.id})
        self.assertNotIn(order, new_delivery._get_candidate_orders(),
                         "an order being corrected must not show up as ready for delivery again")
