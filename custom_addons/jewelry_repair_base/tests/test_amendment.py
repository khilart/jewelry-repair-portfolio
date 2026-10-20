"""
Tests for the editing lock on delivered orders and for "Unlock for Editing".

Scenarios:
  1. A delivered order is read-only for a manager — order fields and every kind of line
  2. Workflow fields stay writable so delivery and billing can still stamp the order
  3. The metal rate button cannot bypass the lock
  4. Only a manager may unlock, and only a delivered order that is still locked
  5. Unlocking makes the order editable, records who and why, and keeps it delivered
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


# post_install so fields contributed by the metal and billing modules are in the registry.
@tagged("post_install", "-at_install")
class TestOrderAmendment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({
            "name": "Amendment Manager",
            "login": "test_amendment_manager",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("jewelry_repair_base.group_jewelry_repair_manager").id,
            ])],
        })
        cls.receptionist = cls.env["res.users"].create({
            "name": "Amendment Receptionist",
            "login": "test_amendment_receptionist",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("jewelry_repair_base.group_jewelry_repair_receptionist").id,
            ])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "Amendment Customer"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Amendment Ring"})
        service_template = cls.env["product.template"].create({
            "name": "Amendment Service",
            "type": "service",
            "list_price": 100.0,
            "repair_service_ok": True,
        })
        cls.service_product = service_template.product_variant_ids[0]

        # Fixtures for the area loss recomputation test
        cls.env["ir.config_parameter"].sudo().set_param(
            "jewelry_repair_base.weight_tracking_mode", "all"
        )
        cls.op_first = cls.env["jewelry.repair.operation"].create({
            "name": "Amendment Casting",
            "area_id": cls.env.ref("jewelry_repair_base.work_area_casting").id,
            "sequence": 10,
        })
        cls.op_second = cls.env["jewelry.repair.operation"].create({
            "name": "Amendment Polishing",
            "area_id": cls.env.ref("jewelry_repair_base.work_area_polishing").id,
            "sequence": 40,
        })
        uom_g = cls.env.ref("uom.product_uom_gram")
        material_template = cls.env["product.template"].create({
            "name": "Amendment Gold",
            "type": "consu",
            "uom_id": uom_g.id,
            "uom_po_id": uom_g.id,
            "repair_material_ok": True,
        })
        cls.material_product = material_template.product_variant_ids[0]
        cls.uom_g = uom_g

    def _delivered_order(self):
        """A delivered order with one service line, built as admin before the lock applies."""
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Amendment Service",
            "quantity": 1.0,
            "price_unit": 100.0,
        })
        order.state = "delivered"
        return order

    # ── the lock ─────────────────────────────────────────────────────────────
    def test_delivered_order_is_locked_for_manager(self):
        order = self._delivered_order().with_user(self.manager)
        with self.assertRaises(UserError):
            order.write({"description": "changed"})

    def test_delivered_order_lines_are_locked(self):
        order = self._delivered_order().with_user(self.manager)
        with self.assertRaises(UserError):
            order.service_line_ids.write({"price_unit": 150.0})
        with self.assertRaises(UserError):
            order.service_line_ids.unlink()
        with self.assertRaises(UserError):
            self.env["jewelry.repair.service.line"].with_user(self.manager).create({
                "order_id": order.id,
                "product_id": self.service_product.id,
                "name": "Extra",
                "quantity": 1.0,
                "price_unit": 10.0,
            })

    def test_workflow_fields_stay_writable(self):
        """Delivery and billing stamp the order after it is delivered — that must keep working."""
        order = self._delivered_order().with_user(self.manager)
        order.write({"current_location_type": "delivered"})
        self.assertEqual(order.current_location_type, "delivered")

    def test_undelivered_order_is_editable(self):
        order = self._delivered_order()
        order.state = "ready"
        order.with_user(self.manager).write({"description": "changed"})
        self.assertEqual(order.description, "changed")

    def test_metal_rate_button_is_blocked(self):
        order = self._delivered_order().with_user(self.manager)
        with self.assertRaises(UserError):
            order.action_apply_metal_rate_to_materials()
        with self.assertRaises(UserError):
            order.action_open_apply_metal_rate_wizard()

    # ── unlocking ────────────────────────────────────────────────────────────
    def test_unlock_requires_a_manager(self):
        order = self._delivered_order().with_user(self.receptionist)
        with self.assertRaises(UserError):
            order.action_open_amendment()

    def test_unlock_rejects_an_order_that_is_not_delivered(self):
        order = self._delivered_order()
        order.state = "ready"
        with self.assertRaises(UserError):
            order.with_user(self.manager).action_open_amendment()

    def test_unlock_rejects_an_already_unlocked_order(self):
        order = self._delivered_order().with_user(self.manager)
        order._open_amendment("first")
        with self.assertRaises(UserError):
            order.action_open_amendment()

    def test_unlock_makes_the_order_editable(self):
        order = self._delivered_order().with_user(self.manager)
        order._open_amendment("wrong price")

        self.assertTrue(order.amendment_open)
        self.assertEqual(order.amendment_reason, "wrong price")
        self.assertEqual(order.amendment_user_id, self.manager)
        self.assertTrue(order.amendment_at)

        order.write({"description": "corrected"})
        order.service_line_ids.write({"price_unit": 150.0})
        self.assertEqual(order.description, "corrected")
        self.assertEqual(order.amount_total, 150.0)

    def test_unlock_keeps_the_order_delivered(self):
        """The order must never leave 'delivered', or it falls out of the document chain."""
        order = self._delivered_order().with_user(self.manager)
        order._open_amendment("wrong price")
        self.assertEqual(order.state, "delivered")

    def test_unlock_is_recorded_in_the_chatter(self):
        order = self._delivered_order().with_user(self.manager)
        order._open_amendment("wrong price")
        self.assertIn("wrong price", order.message_ids[:1].body)

    # ── closing the amendment ────────────────────────────────────────────────
    def _delivered_order_with_area_losses(self):
        """A delivered order whose area losses were computed on the way to 'ready'."""
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
        })
        first_op = self.env["jewelry.repair.order.operation"].create({
            "order_id": order.id,
            "operation_id": self.op_first.id,
            "sequence": self.op_first.sequence,
            "weight_before": 10.0,
            "state": "done",
        })
        self.env["jewelry.repair.order.operation"].create({
            "order_id": order.id,
            "operation_id": self.op_second.id,
            "sequence": self.op_second.sequence,
            "weight_before": 9.0,
            "state": "done",
        })
        order.write({"state": "ready", "delivered_weight": 8.0})
        order.state = "delivered"
        return order, first_op

    def test_closing_the_amendment_recomputes_area_losses(self):
        order, first_op = self._delivered_order_with_area_losses()
        first_area = order.area_loss_ids.filtered(
            lambda row: row.area_id == self.op_first.area_id
        )
        self.assertTrue(first_area, "the order must have area losses to start with")
        before = first_area.loss

        order = order.with_user(self.manager)
        order._open_amendment("material was forgotten")
        self.env["jewelry.repair.material.line"].with_user(self.manager).create({
            "order_id": order.id,
            "order_operation_id": first_op.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": 2.0,
            "consume_from_stock": True,
        })

        self.assertEqual(
            order.area_loss_ids.filtered(lambda r: r.area_id == self.op_first.area_id).loss,
            before,
            "area losses are stored rows: adding a material does not refresh them",
        )

        order._close_amendment()

        self.assertFalse(order.amendment_open)
        self.assertNotEqual(
            order.area_loss_ids.filtered(lambda r: r.area_id == self.op_first.area_id).loss,
            before,
            "closing the amendment must rebuild the area losses",
        )

    def test_wizard_summary_is_empty_without_documents(self):
        order = self._delivered_order()
        wizard = self.env["jewelry.repair.amendment.wizard"].with_user(self.manager).create({
            "order_id": order.id,
            "reason": "wrong price",
        })
        self.assertFalse(wizard.document_summary)
        wizard.action_confirm()
        self.assertTrue(order.amendment_open)
