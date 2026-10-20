"""
Tests for jewelry.order.area.loss calculation (_compute_area_losses).

Scenarios:
  1. Repair, no gems, no materials — pure metal loss per area
  2. Repair with gem setting — gem_weight subtracted from gem area weight_out and beyond
  3. Repair with material added (solder) — material weight subtracted from subsequent areas
  4. New product manufacturing — casting weighed like any other area
  5. New product manufacturing + gem setting — combined adjustments
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


# Runs post_install so fields contributed by jewelry_metal_accounting
# (e.g. operation.executor_metal_storage_id, used by the material line
# create hook) are present in the registry.
@tagged("post_install", "-at_install")
class TestAreaLoss(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # These scenarios cover repair orders, so weight tracking must apply to
        # every order regardless of the mode configured in the live database.
        cls.env["ir.config_parameter"].sudo().set_param(
            "jewelry_repair_base.weight_tracking_mode", "all"
        )

        # Work areas from pre-installed data
        cls.area_casting = cls.env.ref("jewelry_repair_base.work_area_casting")
        cls.area_mechanical = cls.env.ref("jewelry_repair_base.work_area_mechanical")
        cls.area_gem = cls.env.ref("jewelry_repair_base.work_area_gem_setting")
        cls.area_polishing = cls.env.ref("jewelry_repair_base.work_area_polishing")

        # Operation types
        cls.op_casting = cls.env["jewelry.repair.operation"].create({
            "name": "Test Casting",
            "area_id": cls.area_casting.id,
            "sequence": 10,
        })
        cls.op_mechanical = cls.env["jewelry.repair.operation"].create({
            "name": "Test Mechanical",
            "area_id": cls.area_mechanical.id,
            "sequence": 20,
        })
        cls.op_gem = cls.env["jewelry.repair.operation"].create({
            "name": "Test Gem Setting",
            "area_id": cls.area_gem.id,
            "is_gem_setting": True,
            "sequence": 30,
        })
        cls.op_polishing = cls.env["jewelry.repair.operation"].create({
            "name": "Test Polishing",
            "area_id": cls.area_polishing.id,
            "sequence": 40,
        })

        # Partner and item type
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({
            "name": "Test Ring",
        })

        # Gem type for gem lines
        cls.gem_type = cls.env["jewelry.gem.type"].create({
            "name": "Test Diamond",
        })

        # Product for material lines
        uom_g = cls.env.ref("uom.product_uom_gram")
        product_tmpl = cls.env["product.template"].create({
            "name": "Test Gold",
            "type": "consu",
            "uom_id": uom_g.id,
            "uom_po_id": uom_g.id,
            "repair_material_ok": True,
        })
        cls.material_product = product_tmpl.product_variant_ids[0]
        cls.uom_g = uom_g

    # ── helpers ────────────────────────────────────────────────────────────────

    def _make_order(self, new_product_manufacturing=False, delivered_weight=0.0):
        return self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "new_product_manufacturing": new_product_manufacturing,
            "delivered_weight": delivered_weight,
        })

    def _add_op(self, order, op_type, weight_before):
        return self.env["jewelry.repair.order.operation"].create({
            "order_id": order.id,
            "operation_id": op_type.id,
            "sequence": op_type.sequence,
            "weight_before": weight_before,
            "state": "done",
        })

    def _add_gem(self, order, total_weight_g):
        # total_weight_g = quantity * weight_ct * 0.2  →  weight_ct = total_weight_g / 0.2
        self.env["jewelry.repair.gem.line"].create({
            "order_id": order.id,
            "gem_type_id": self.gem_type.id,
            "quantity": 1,
            "weight_ct": total_weight_g / 0.2,
        })

    def _add_material(self, order, op, weight):
        return self.env["jewelry.repair.material.line"].create({
            "order_id": order.id,
            "order_operation_id": op.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": weight,
            "consume_from_stock": True,
        })

    def _add_return(self, order, op, weight):
        self.env["jewelry.repair.material.line"].create({
            "order_id": order.id,
            "order_operation_id": op.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": weight,
            "return_to_storage": True,
        })

    def _losses(self, order):
        """Return dict {area_name: (weight_in, weight_out, loss)} after recalculation."""
        order._compute_area_losses()
        return {
            rec.area_id.name: (
                round(rec.weight_in, 3),
                round(rec.weight_out, 3),
                round(rec.loss, 3),
            )
            for rec in order.area_loss_ids
        }

    # ── tests ──────────────────────────────────────────────────────────────────

    def test_single_operation_recalculates_on_delivered_weight_change(self):
        """Single operation: weight_out must update when delivered_weight is set after ready."""
        order = self._make_order(delivered_weight=0.0)
        self._add_op(order, self.op_mechanical, weight_before=10.0)
        order._compute_area_losses()

        # Before delivered_weight is set: weight_out is 0, loss = weight_in (wrong but stored)
        losses_before = self._losses(order)
        self.assertIn("Mechanical Processing", losses_before)
        self.assertEqual(losses_before["Mechanical Processing"][1], 0.0)  # weight_out = 0

        # Simulate setting delivered_weight (triggers write() → _compute_area_losses)
        order.write({"state": "ready", "delivered_weight": 9.7})

        losses_after = {
            rec.area_id.name: (round(rec.weight_in, 3), round(rec.weight_out, 3), round(rec.loss, 3))
            for rec in order.area_loss_ids
        }
        self.assertEqual(losses_after["Mechanical Processing"], (10.0, 9.7, 0.3))

    def test_repair_no_gems_no_materials(self):
        """Pure metal loss: weight_before flows directly through area boundaries."""
        order = self._make_order(delivered_weight=9.5)
        self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_op(order, self.op_polishing, weight_before=9.8)

        losses = self._losses(order)

        # Mechanical: in=10.0, out=9.8 (weight_before of polishing)
        self.assertEqual(losses["Mechanical Processing"], (10.0, 9.8, 0.2))
        # Polishing: in=9.8, out=9.5 (delivered_weight)
        self.assertEqual(losses["Polishing"], (9.8, 9.5, 0.3))

    def test_repair_gem_weight_adjustment(self):
        """Gem weight is subtracted from weight_out of gem area and all subsequent areas."""
        order = self._make_order(delivered_weight=11.5)
        self._add_gem(order, total_weight_g=1.0)

        self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_op(order, self.op_gem, weight_before=9.8)
        self._add_op(order, self.op_polishing, weight_before=11.5)  # includes gems (1.0g)

        losses = self._losses(order)

        # Mechanical: no gem adj yet → in=10.0, out=9.8 (weight_before of gem area)
        self.assertEqual(losses["Mechanical Processing"], (10.0, 9.8, 0.2))

        # Gem Setting: in=9.8 (metal only), out=11.5-1.0=10.5 (next area raw - gem_weight)
        self.assertEqual(losses["Gem Setting"], (9.8, 10.5, -0.7))

        # Polishing: in=11.5-1.0=10.5, out=11.5-1.0=10.5
        self.assertEqual(losses["Polishing"], (10.5, 10.5, 0.0))

    def test_repair_material_addition(self):
        """Material added during mechanical is subtracted from subsequent area weights."""
        order = self._make_order(delivered_weight=10.1)
        op_mech = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_op(order, self.op_polishing, weight_before=10.3)  # includes 0.2g solder
        self._add_material(order, op_mech, weight=0.2)

        losses = self._losses(order)

        # Mechanical: in=10.0, out=10.3-0.2=10.1 (solder added here, subtract from out)
        self.assertEqual(losses["Mechanical Processing"], (10.0, 10.1, -0.1))

        # Polishing: in=10.3-0.2=10.1, out=10.1-0.2=9.9
        self.assertEqual(losses["Polishing"], (10.1, 9.9, 0.2))

    def test_new_product_manufacturing_casting(self):
        """Casting is an area like any other: weight_before against the next area's."""
        order = self._make_order(new_product_manufacturing=True, delivered_weight=9.5)
        self._add_op(order, self.op_casting, weight_before=10.0)
        self._add_op(order, self.op_mechanical, weight_before=9.8)

        losses = self._losses(order)

        # Casting: in=10.0 (weighed by the master), out=9.8 (weight_before mechanical)
        self.assertEqual(losses["Casting"], (10.0, 9.8, 0.2))
        self.assertEqual(losses["Mechanical Processing"], (9.8, 9.5, 0.3))

    def test_casting_material_is_an_ordinary_addition(self):
        """Metal consumed on a casting operation is an addition, not the area's input."""
        order = self._make_order(new_product_manufacturing=True, delivered_weight=9.5)
        op_cast = self._add_op(order, self.op_casting, weight_before=10.0)
        self._add_op(order, self.op_mechanical, weight_before=9.8)
        self._add_material(order, op_cast, weight=0.3)

        losses = self._losses(order)

        # Casting: in=10.0, out=9.8-0.3=9.5
        self.assertEqual(losses["Casting"], (10.0, 9.5, 0.5))
        # Mechanical: in=9.8-0.3=9.5, out=9.5-0.3=9.2
        self.assertEqual(losses["Mechanical Processing"], (9.5, 9.2, 0.3))

    def test_casting_without_weight_drops_out_of_the_route(self):
        """An unweighed casting operation is skipped, as in every other area."""
        order = self._make_order(new_product_manufacturing=True, delivered_weight=9.5)
        op_cast = self._add_op(order, self.op_casting, weight_before=0.0)
        self._add_op(order, self.op_mechanical, weight_before=9.8)
        self._add_material(order, op_cast, weight=10.0)

        losses = self._losses(order)

        # The operation is out of the route, so the material hanging off it is out too.
        self.assertNotIn("Casting", losses)
        self.assertEqual(losses["Mechanical Processing"], (9.8, 9.5, 0.3))

    def test_new_product_manufacturing_casting_with_gems(self):
        """New product: casting weighed like any area + gem adjustment in later areas."""
        order = self._make_order(new_product_manufacturing=True, delivered_weight=11.0)
        self._add_gem(order, total_weight_g=1.0)

        self._add_op(order, self.op_casting, weight_before=10.0)
        self._add_op(order, self.op_mechanical, weight_before=9.5)
        self._add_op(order, self.op_gem, weight_before=9.3)
        self._add_op(order, self.op_polishing, weight_before=10.1)  # includes 1.0g gems

        losses = self._losses(order)

        # Casting: in=10.0, out=9.5
        self.assertEqual(losses["Casting"], (10.0, 9.5, 0.5))
        # Mechanical: in=9.5, out=9.3 (weight_before gem, no gem adj yet)
        self.assertEqual(losses["Mechanical Processing"], (9.5, 9.3, 0.2))
        # Gem Setting: in=9.3, out=10.1-1.0=9.1
        self.assertEqual(losses["Gem Setting"], (9.3, 9.1, 0.2))
        # Polishing: in=10.1-1.0=9.1, out=11.0-1.0=10.0
        self.assertEqual(losses["Polishing"], (9.1, 10.0, -0.9))

    def test_return_to_storage_reduces_loss(self):
        """Metal returned to storage during an operation must not inflate that area's loss."""
        # Piece: 10g → mechanical removes 2g to storage, polishes, delivered 7.5g
        # Actual losses: mechanical 0.5g (10-2-7.5=0.5 total, split below), polishing 0g
        order = self._make_order(delivered_weight=7.5)
        op_mech = self._add_op(order, self.op_mechanical, weight_before=10.0)
        # After mechanical: 2g returned to storage → next area weighs 7.5g (10 - 2 - 0.5 loss)
        self._add_op(order, self.op_polishing, weight_before=7.5)
        self._add_return(order, op_mech, weight=2.0)

        losses = self._losses(order)

        # Mechanical: in=10.0, out=7.5+2.0=9.5, loss=0.5
        self.assertEqual(losses["Mechanical Processing"], (10.0, 9.5, 0.5))
        # Polishing: in=7.5+2.0=9.5, out=7.5+2.0=9.5, loss=0.0
        self.assertEqual(losses["Polishing"], (9.5, 9.5, 0.0))

    def test_return_to_storage_combined_with_material(self):
        """Return to storage and material addition in the same area work independently."""
        # Mechanical: adds 1g solder, returns 2g to storage
        # Polishing: pure loss 0.3g
        order = self._make_order(delivered_weight=8.8)
        op_mech = self._add_op(order, self.op_mechanical, weight_before=10.0)
        # After mechanical: piece = 10 + 1 (solder) - 2 (return) - 0.2 (loss) = 8.8, but
        # polishing weight_before reflects 8.8+0 = 8.8 because no further loss there.
        # Actually let's say mechanical itself has 0 loss, polishing has 0.3 loss.
        # piece after mechanical = 10 + 1 - 2 = 9.0, polishing weight_before = 9.0, delivered = 8.7
        order.write({"delivered_weight": 8.7})
        self._add_op(order, self.op_polishing, weight_before=9.0)
        self._add_material(order, op_mech, weight=1.0)
        self._add_return(order, op_mech, weight=2.0)

        losses = self._losses(order)

        # Mechanical: in=10.0, out=9.0-1.0+2.0=10.0, loss=0.0
        self.assertEqual(losses["Mechanical Processing"], (10.0, 10.0, 0.0))
        # Polishing: in=9.0-1.0+2.0=10.0, out=8.7-1.0+2.0=9.7, loss=0.3
        self.assertEqual(losses["Polishing"], (10.0, 9.7, 0.3))


@tagged("post_install", "-at_install")
class TestWeightDiscrepancy(TestAreaLoss):
    """Tests for _metal_balance and the acceptance-time discrepancy warning."""

    def test_returned_metal_is_not_a_discrepancy(self):
        """Metal sent back to storage leaves the item but is not lost."""
        order = self._make_order(delivered_weight=8.0)
        order.received_weight = 10.0
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_return(order, op, weight=1.9)

        weight_in, weight_out, loss, percent = order._metal_balance()
        self.assertEqual(round(weight_in, 3), 10.0)
        self.assertEqual(round(weight_out, 3), 9.9)
        self.assertEqual(round(loss, 3), 0.1)
        self.assertEqual(round(percent, 2), 1.0)
        self.assertIsNone(order._check_weight_discrepancy())

    def test_workshop_metal_added_is_not_a_discrepancy(self):
        """Metal taken from stock and left in the item is input, not a weight jump."""
        order = self._make_order(delivered_weight=11.0)
        order.received_weight = 10.0
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0)

        weight_in, weight_out, loss, _percent = order._metal_balance()
        self.assertEqual(round(weight_in, 3), 11.0)
        self.assertEqual(round(weight_out, 3), 11.0)
        self.assertEqual(round(loss, 3), 0.0)
        self.assertIsNone(order._check_weight_discrepancy())

    def test_invoiced_material_stays_out_of_the_balance(self):
        """Material billed to the client is sold metal, not workshop input."""
        order = self._make_order(delivered_weight=11.0)
        order.received_weight = 10.0
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0).include_in_invoice = True

        weight_in, _weight_out, _loss, _percent = order._metal_balance()
        self.assertEqual(round(weight_in, 3), 10.0)
        self.assertIsNotNone(order._check_weight_discrepancy())

    def test_real_loss_still_warns(self):
        """A genuine 10% loss on a repair order is still over the 5% threshold."""
        order = self._make_order(delivered_weight=9.0)
        order.received_weight = 10.0
        self._add_op(order, self.op_mechanical, weight_before=10.0)

        message = order._check_weight_discrepancy()
        self.assertIsNotNone(message)
        self.assertIn("10.0%", message)


@tagged("post_install", "-at_install")
class TestClientLoss(TestAreaLoss):
    """Tests for the jewelry.order.client.loss SQL view."""

    def _client_loss(self, order):
        self.env.flush_all()
        return self.env["jewelry.order.client.loss"].search([("order_id", "=", order.id)])

    def _make_delivered_order(self, received_weight, delivered_weight):
        order = self._make_order(delivered_weight=delivered_weight)
        order.write({"received_weight": received_weight, "state": "delivered"})
        return order

    def test_returned_weight_reduces_loss(self):
        """Metal returned to storage (sprue) must not be counted as loss."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=8.0)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_return(order, op, weight=1.5)

        row = self._client_loss(order)
        self.assertEqual(round(row.returned_weight, 3), 1.5)
        self.assertEqual(round(row.loss, 3), 0.5)
        self.assertEqual(round(row.loss_percent, 2), 5.0)

    def test_consumed_material_counts_as_added(self):
        """Material consumed from stock is metal put in, not metal returned."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=10.8)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0)

        row = self._client_loss(order)
        self.assertEqual(round(row.returned_weight, 3), 0.0)
        self.assertEqual(round(row.added_weight, 3), 1.0)
        # loss = 10.0 in + 1.0 added - 10.8 out = 0.2, over an 11.0 g input
        self.assertEqual(round(row.loss, 3), 0.2)
        self.assertEqual(round(row.loss_percent, 2), 1.82)

    def test_invoiced_material_is_not_added(self):
        """Material billed to the client is sold metal, not workshop metal put in."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=10.8)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0).include_in_invoice = True

        row = self._client_loss(order)
        self.assertEqual(round(row.added_weight, 3), 0.0)
        self.assertEqual(round(row.invoiced_weight, 3), 1.0)
        self.assertEqual(round(row.loss, 3), -0.8)

    def test_invoiced_counts_lines_not_taken_from_stock(self):
        """Billed metal counts whether or not it was written off from stock."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=12.0)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0).include_in_invoice = True
        self._add_material(order, op, weight=2.0).write({
            "include_in_invoice": True,
            "consume_from_stock": False,
        })

        row = self._client_loss(order)
        self.assertEqual(round(row.invoiced_weight, 3), 3.0)
        # Neither line is workshop metal, so the loss balance is untouched by them
        self.assertEqual(round(row.added_weight, 3), 0.0)
        self.assertEqual(round(row.loss, 3), -2.0)

    def test_added_and_returned_together(self):
        """Added and returned metal are independent columns of the same balance."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=9.3)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_material(order, op, weight=1.0)
        self._add_return(order, op, weight=1.5)

        row = self._client_loss(order)
        self.assertEqual(round(row.added_weight, 3), 1.0)
        self.assertEqual(round(row.returned_weight, 3), 1.5)
        # loss = 10.0 + 1.0 - 9.3 - 1.5 = 0.2
        self.assertEqual(round(row.loss, 3), 0.2)

    def test_loss_sign(self):
        """loss_sign splits real losses from data-entry errors and clean balances."""
        losing = self._make_delivered_order(received_weight=10.0, delivered_weight=9.5)
        gaining = self._make_delivered_order(received_weight=10.0, delivered_weight=10.5)
        balanced = self._make_delivered_order(received_weight=10.0, delivered_weight=10.0)

        self.assertEqual(self._client_loss(losing).loss_sign, "loss")
        self.assertEqual(self._client_loss(gaining).loss_sign, "gain")
        self.assertEqual(self._client_loss(balanced).loss_sign, "zero")

    def test_loss_sign_invalid_when_weight_missing(self):
        """Orders delivered without a weight entered are flagged, not counted as 100% loss."""
        no_out = self._make_delivered_order(received_weight=10.0, delivered_weight=0.0)
        no_in = self._make_delivered_order(received_weight=0.0, delivered_weight=9.5)

        self.assertEqual(self._client_loss(no_out).loss_sign, "invalid")
        self.assertEqual(self._client_loss(no_in).loss_sign, "invalid")

    def test_loss_sign_invalid_when_gems_exceed_delivered_weight(self):
        """Gems recorded while the delivered weight is blank push metal out below zero."""
        order = self._make_delivered_order(received_weight=0.001, delivered_weight=0.0)
        self._add_gem(order, total_weight_g=1.6)

        row = self._client_loss(order)
        self.assertLess(row.metal_delivered_weight, 0.0)
        self.assertEqual(row.loss_sign, "invalid")

    def test_returned_weight_with_gems(self):
        """Gems leave the outgoing weight, returns leave the loss — both at once."""
        order = self._make_delivered_order(received_weight=10.0, delivered_weight=9.0)
        op = self._add_op(order, self.op_mechanical, weight_before=10.0)
        self._add_gem(order, total_weight_g=1.0)
        self._add_return(order, op, weight=1.5)

        row = self._client_loss(order)
        # metal out = 9.0 - 1.0 gems = 8.0; loss = 10.0 - 8.0 - 1.5 = 0.5
        self.assertEqual(round(row.metal_delivered_weight, 3), 8.0)
        self.assertEqual(round(row.returned_weight, 3), 1.5)
        self.assertEqual(round(row.loss, 3), 0.5)
