"""Metal and stone prices are quoted in whole units, so the derived price of a
piece is rounded arithmetically once it has been calculated.
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPriceRounding(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Rounding Test Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Test Ring"})
        cls.order = cls.env["jewelry.repair.order"].create({
            "partner_id": cls.partner.id,
            "item_type_id": cls.item_type.id,
        })
        cls.gem_type = cls.env["jewelry.gem.type"].create({"name": "Test Sapphire"})

    def _gem_line(self, **vals):
        return self.env["jewelry.repair.gem.line"].create(dict({
            "order_id": self.order.id,
            "gem_type_id": self.gem_type.id,
            "quantity": 1,
        }, **vals))

    # ── stones ───────────────────────────────────────────────────────────────
    def test_gem_piece_price_is_rounded_down(self):
        line = self._gem_line(price_per_ct=100.0, weight_ct=1.234)

        self.assertEqual(line.subtotal, 123.0)

    def test_gem_piece_price_is_rounded_up(self):
        line = self._gem_line(price_per_ct=100.0, weight_ct=1.236)

        self.assertEqual(line.subtotal, 124.0)

    def test_gem_half_rounds_away_from_zero(self):
        line = self._gem_line(price_per_ct=100.0, weight_ct=1.235)

        self.assertEqual(line.subtotal, 124.0)

    def test_gem_subtotal_stays_whole_for_several_stones(self):
        line = self._gem_line(price_per_ct=100.0, weight_ct=1.234, quantity=3)

        self.assertEqual(line.subtotal, 369.0)

    def test_gem_manual_price_is_kept_as_typed(self):
        line = self._gem_line(price_unit=123.45)

        self.assertEqual(line.subtotal, 123.45)

    # ── metal ────────────────────────────────────────────────────────────────
    def _metal_line_vals(self, weight, quantity=1.0):
        """Metal priced by hand: 100 per fine gram, alloy of purity 0.5."""
        metal = self.env["jewelry.metal"].create({"name": "Test Gold", "code": "TAU"})
        alloy = self.env["jewelry.metal.alloy"].create({
            "name": "Test 500", "code": "T500", "metal_id": metal.id, "purity": 0.5,
        })
        line = self.env["jewelry.repair.material.line"].new({
            "order_id": self.order.id,
            "alloy_id": alloy.id,
            "quantity": quantity,
            "rate_manual": True,
            "rate_price_per_gram": 100.0,
            "weight": weight,
        })
        return line._prepare_metal_rate_pricing_vals()

    def test_metal_unit_price_is_rounded_down(self):
        # 100 × 0.5 × 2.468 = 123.4
        self.assertEqual(self._metal_line_vals(2.468)["price_unit"], 123.0)

    def test_metal_unit_price_is_rounded_up(self):
        # 100 × 0.5 × 2.472 = 123.6
        self.assertEqual(self._metal_line_vals(2.472)["price_unit"], 124.0)

    def test_metal_half_rounds_away_from_zero(self):
        # 100 × 0.5 × 2.47 = 123.5
        self.assertEqual(self._metal_line_vals(2.47)["price_unit"], 124.0)

    def test_metal_rate_itself_is_not_rounded(self):
        vals = self._metal_line_vals(2.468)

        self.assertEqual(vals["rate_price_per_gram"], 100.0)

    def test_metal_unit_price_is_rounded_after_splitting_by_quantity(self):
        # 100 × 0.5 × 4.936 = 246.8, split over two pieces → 123.4 each
        self.assertEqual(self._metal_line_vals(4.936, quantity=2.0)["price_unit"], 123.0)
