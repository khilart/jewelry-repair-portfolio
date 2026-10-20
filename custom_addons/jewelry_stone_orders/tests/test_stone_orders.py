"""The stone order carries a request to a supplier and what actually came back,
without letting either side quietly overwrite the other.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStoneOrders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # No customer_rank on these partners: the field comes from `sale`, which a
        # clean install of this module does not pull in.
        cls.supplier = cls.env["res.partner"].create({
            "name": "Stone Supplier",
            "is_stone_supplier": True,
            "stone_commission_pct": 10.0,
        })
        cls.client = cls.env["res.partner"].create({"name": "Stone Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Stone Ring"})
        cls.gem_type = cls.env["jewelry.gem.type"].create({"name": "Test Diamond"})
        cls.client_order = cls._repair_order(cls.client)
        cls.supplier_order = cls._repair_order(cls.supplier)

    @classmethod
    def _repair_order(cls, partner):
        return cls.env["jewelry.repair.order"].create({
            "partner_id": partner.id,
            "item_type_id": cls.item_type.id,
        })

    def _request_values(self, **vals):
        return dict({
            "gem_type_id": self.gem_type.id,
            "origin": "natural",
            "quantity": 12,
            "weight_ct": 0.1692,
        }, **vals)

    def _stone_order(self, **vals):
        return self.env["jewelry.stone.order"].create(dict({
            "supplier_id": self.supplier.id,
            "repair_order_id": self.client_order.id,
            "request_line_ids": [(0, 0, self._request_values())],
        }, **vals))

    def _ship(self, order, **vals):
        return self.env["jewelry.stone.order.shipped.line"].create(dict({
            "order_id": order.id,
            "gem_type_id": self.gem_type.id,
            "origin": "natural",
            "quantity": 1,
            "weight_ct": 0.17,
        }, **vals))

    # ── Certificates ──

    def test_certificate_covers_a_single_stone(self):
        """Twelve stones under one number would never reconcile with the supplier."""
        with self.assertRaises(ValidationError):
            self._stone_order(request_line_ids=[
                (0, 0, self._request_values(quantity=2, certificate_ref="GIA-1")),
            ])

    def test_melee_needs_no_certificate(self):
        order = self._stone_order()
        self.assertEqual(order.request_line_ids.quantity, 12)

    # ── Who pays ──

    def test_payable_when_the_client_is_not_the_supplier(self):
        self.assertEqual(self._stone_order().stones_payable, "yes")

    def test_not_payable_on_the_suppliers_own_order(self):
        order = self._stone_order(repair_order_id=self.supplier_order.id)
        self.assertEqual(order.stones_payable, "no")

    def test_stock_order_is_always_payable(self):
        order = self._stone_order(purpose="stock", repair_order_id=False)
        self.assertEqual(order.stones_payable, "yes")

    def test_manual_choice_survives_a_change_of_customer(self):
        """A default, not a compute: recomputing would silently undo the manager."""
        order = self._stone_order(repair_order_id=self.supplier_order.id)
        order.stones_payable = "yes"
        self.supplier_order.partner_id = self.client
        order.invalidate_recordset()
        self.assertEqual(order.stones_payable, "yes")

    def test_commission_is_a_snapshot(self):
        order = self._stone_order()
        self.supplier.stone_commission_pct = 25.0
        order.invalidate_recordset()
        self.assertEqual(order.commission_pct, 10.0)

    # ── Purpose ──

    def test_stock_order_rejects_a_repair_order(self):
        with self.assertRaises(ValidationError):
            self._stone_order(purpose="stock")

    def test_repair_order_is_required_for_a_repair_purpose(self):
        with self.assertRaises(ValidationError):
            self._stone_order(repair_order_id=False)

    # ── State machine ──

    def test_a_request_cannot_omit_the_origin(self):
        """Caught on entry rather than at confirmation: the supplier must never be
        left to guess between a natural stone and a grown one.
        """
        with self.assertRaises(Exception):
            self._stone_order(request_line_ids=[
                (0, 0, self._request_values(origin=False)),
            ])

    def test_confirm_needs_something_to_request(self):
        order = self._stone_order()
        order.request_line_ids.unlink()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_requested_lines_are_frozen_once_confirmed(self):
        order = self._stone_order()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.request_line_ids.write({"quantity": 5})

    def test_back_to_draft_only_before_the_supplier_takes_it(self):
        order = self._stone_order()
        order.action_confirm()
        order.action_reset_to_draft()
        self.assertEqual(order.state, "draft")
        order.action_confirm()
        order.action_set_in_progress()
        with self.assertRaises(UserError):
            order.action_reset_to_draft()

    def test_shipping_straight_from_confirmed(self):
        """In Progress needs a button on the supplier's side and may never appear."""
        order = self._stone_order()
        order.action_confirm()
        order.action_mark_shipped()
        self.assertEqual(order.state, "shipped")

    def test_rejection_carries_a_reason(self):
        order = self._stone_order()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_reject("  ")
        order.action_reject("Out of stock")
        self.assertEqual(order.state, "rejected")

    # ── Completeness ──

    def test_short_shipment_is_visible(self):
        order = self._stone_order()
        order.action_confirm()
        self._ship(order, request_line_id=order.request_line_ids.id, quantity=8)
        order.invalidate_recordset()
        self.assertFalse(order.shipped_complete)
        self._ship(order, request_line_id=order.request_line_ids.id, quantity=4)
        order.invalidate_recordset()
        self.assertTrue(order.shipped_complete)

    def test_request_the_remainder(self):
        order = self._stone_order()
        order.action_confirm()
        self._ship(order, request_line_id=order.request_line_ids.id, quantity=8)
        order.action_mark_shipped()
        order.action_receive()
        action = order.action_request_remainder()
        remainder = self.env["jewelry.stone.order"].browse(action["res_id"])
        self.assertEqual(remainder.state, "draft")
        self.assertEqual(remainder.request_line_ids.quantity, 4)

    # ── Money ──

    def test_commission_splits_the_client_price(self):
        order = self._stone_order()
        order.action_confirm()
        self._ship(order, quantity=10, price_unit=100.0)
        order.invalidate_recordset()
        self.assertEqual(order.amount_supplier, 900.0)

    def test_a_return_reduces_what_we_owe(self):
        order = self._stone_order()
        order.action_confirm()
        kept = self._ship(order, quantity=2, price_unit=100.0)
        sent_back = self._ship(order, quantity=8, price_unit=100.0)
        order.action_mark_shipped()
        order.action_receive()
        doc = self.env["jewelry.stone.return"].create({
            "stone_order_id": order.id,
            "line_ids": [(0, 0, {"shipped_line_id": sent_back.id})],
        })
        doc.action_post()
        order.invalidate_recordset()
        self.assertEqual(sent_back.disposal, "returned")
        self.assertEqual(order.amount_supplier, 180.0)
        self.assertTrue(kept.id)

    def test_a_broken_stone_names_who_carries_it(self):
        order = self._stone_order()
        order.action_confirm()
        line = self._ship(order)
        with self.assertRaises(ValidationError):
            line.write({"disposal": "broken"})

    # ── Transfer into the repair order ──

    def _received_order_with_stones(self):
        order = self._stone_order()
        order.action_confirm()
        for ref in ("GIA-A1", "GIA-A2", "GIA-A3"):
            self._ship(order, certificate_ref=ref, price_unit=300.0)
        melee = self._ship(order, quantity=20, weight_ct=0.01, price_unit=5.0)
        order.action_mark_shipped()
        order.action_receive()
        return order, melee

    def test_certified_stones_expand_one_per_line(self):
        """A gem line holds a single certificate, so three stones need three lines."""
        order, _melee = self._received_order_with_stones()
        order._transfer_apply()
        self.client_order.invalidate_recordset()
        certified = self.client_order.gem_line_ids.filtered("certificate_id")
        self.assertEqual(len(certified), 3)
        self.assertEqual(set(certified.mapped("quantity")), {1})
        self.assertEqual(
            sorted(certified.mapped("certificate_id.name")),
            ["GIA-A1", "GIA-A2", "GIA-A3"],
        )

    def test_transfer_carries_the_origin(self):
        order, _melee = self._received_order_with_stones()
        order._transfer_apply()
        self.client_order.invalidate_recordset()
        self.assertTrue(all(self.client_order.gem_line_ids.mapped("origin")))

    def test_transfer_twice_updates_instead_of_duplicating(self):
        order, melee = self._received_order_with_stones()
        order._transfer_apply()
        melee.write({"quantity": 25})
        order._transfer_apply()
        self.client_order.invalidate_recordset()
        self.assertEqual(len(self.client_order.gem_line_ids), 4)
        moved = self.client_order.gem_line_ids.filtered(lambda g: not g.certificate_id)
        self.assertEqual(moved.quantity, 25)

    def test_a_disposed_stone_is_left_out(self):
        order, _melee = self._received_order_with_stones()
        order._transfer_apply()
        broken = order.shipped_line_ids.filtered(lambda l: l.certificate_ref == "GIA-A3")
        self.client_order.gem_line_ids.filtered(
            lambda g: g.stone_order_line_id == broken
        ).unlink()
        broken.write({"disposal": "broken", "broken_charge_to": "workshop"})
        order._transfer_apply()
        self.client_order.invalidate_recordset()
        self.assertEqual(len(self.client_order.gem_line_ids), 3)

    def test_transfer_needs_a_received_order(self):
        order = self._stone_order()
        order.action_confirm()
        with self.assertRaises(UserError):
            order._transfer_apply()

    # ── Change watermark ──

    def test_line_edits_move_the_watermark_and_notes_do_not(self):
        """The supplier polls on this field, not write_date: a row written directly
        leaves the parent's write_date untouched.
        """
        order = self._stone_order()
        order.action_confirm()
        line = self._ship(order)

        order.invalidate_recordset()
        self.assertTrue(order.last_change_at)

        order.write({"last_change_at": False})
        line.write({"quantity": 3})
        order.invalidate_recordset()
        self.assertTrue(order.last_change_at, "editing a shipped line must be visible")

        order.write({"last_change_at": False})
        order.write({"notes": "fixed a typo"})
        order.invalidate_recordset()
        self.assertFalse(order.last_change_at, "a note is nobody else's business")

        order.write({"last_change_at": False})
        line.unlink()
        order.invalidate_recordset()
        self.assertTrue(order.last_change_at, "a removed line must be visible")
