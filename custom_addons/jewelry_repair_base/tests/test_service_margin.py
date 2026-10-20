"""A service line remembers what it costs the workshop, so the difference with the
price the manager negotiated can be read off the order.
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestServiceMargin(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Margin Test Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Margin Ring"})
        cls.order = cls.env["jewelry.repair.order"].create({
            "partner_id": cls.partner.id,
            "item_type_id": cls.item_type.id,
        })
        cls.service = cls.env["product.template"].create({
            "name": "Margin Service",
            "type": "service",
            "list_price": 3000.0,
            "repair_service_ok": True,
        }).product_variant_ids[0]
        cls.other_service = cls.env["product.template"].create({
            "name": "Margin Service Two",
            "type": "service",
            "list_price": 500.0,
            "repair_service_ok": True,
        }).product_variant_ids[0]

    def _line(self, **vals):
        return self.env["jewelry.repair.service.line"].create(dict({
            "order_id": self.order.id,
            "product_id": self.service.id,
            "name": "Margin Service",
            "quantity": 1,
        }, **vals))

    def _picked_line(self, product=None):
        """A line filled the way the form does it — through the product onchange."""
        line = self.env["jewelry.repair.service.line"].new({
            "order_id": self.order.id,
            "product_id": (product or self.service).id,
        })
        line._onchange_product_id()
        return line

    # ── capturing the base ───────────────────────────────────────────────────
    def test_base_is_captured_from_the_list_price(self):
        line = self._picked_line()

        self.assertEqual(line.price_unit, 3000.0)
        self.assertEqual(line.base_price, 3000.0)
        self.assertEqual(line.margin, 0.0)

    def test_base_is_captured_from_the_client_price(self):
        self.env["jewelry.repair.client.price"].create({
            "partner_id": self.partner.id,
            "product_id": self.service.id,
            "discount_percent": 20.0,
        })

        line = self._picked_line()

        self.assertEqual(line.price_unit, 2400.0)
        self.assertEqual(line.base_price, 2400.0)
        self.assertEqual(line.margin, 0.0)

    def test_picking_another_product_recaptures_the_base(self):
        line = self._picked_line()
        self.assertEqual(line.base_price, 3000.0)

        line.product_id = self.other_service
        line._onchange_product_id()

        self.assertEqual(line.base_price, 500.0)

    def test_a_line_built_in_code_falls_back_to_the_sold_price(self):
        line = self._line(price_unit=1800.0)

        self.assertEqual(line.base_price, 1800.0)
        self.assertEqual(line.margin, 0.0)

    # ── margin ───────────────────────────────────────────────────────────────
    def test_raising_the_price_leaves_the_base_alone(self):
        line = self._line(price_unit=3000.0)

        line.price_unit = 3500.0

        self.assertEqual(line.base_price, 3000.0)
        self.assertEqual(line.margin, 500.0)

    def test_selling_below_the_base_gives_a_negative_margin(self):
        line = self._line(price_unit=3000.0)

        line.price_unit = 2400.0

        self.assertEqual(line.margin, -600.0)

    def test_margin_follows_the_quantity(self):
        line = self._line(price_unit=3000.0, quantity=3)

        line.price_unit = 3500.0

        self.assertEqual(line.base_amount, 9000.0)
        self.assertEqual(line.margin, 1500.0)

    # ── outsourcing ──────────────────────────────────────────────────────────
    def test_outsource_cost_overrides_the_base(self):
        line = self._line(price_unit=4000.0)

        line.write({"price_unit": 12000.0, "outsource_cost": 8000.0})

        self.assertEqual(line.base_amount, 8000.0)
        self.assertEqual(line.margin, 4000.0)

    def test_outsource_cost_is_a_line_total(self):
        line = self._line(price_unit=5000.0, quantity=3)

        line.outsource_cost = 9000.0

        self.assertEqual(line.base_amount, 9000.0)
        self.assertEqual(line.margin, 6000.0)

    def test_clearing_the_outsource_cost_restores_the_base(self):
        line = self._line(price_unit=4000.0, outsource_cost=8000.0)
        self.assertEqual(line.base_amount, 8000.0)

        line.outsource_cost = 0.0

        self.assertEqual(line.base_amount, 4000.0)
        self.assertEqual(line.margin, 0.0)
