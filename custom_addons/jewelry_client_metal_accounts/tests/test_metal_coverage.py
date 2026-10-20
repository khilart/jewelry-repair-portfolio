from datetime import datetime

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged("post_install", "-at_install")
class TestMetalCoverage(TransactionCase):
    """Client metal account coverage of repair orders during billing.

    Fixed numbers (purity 0.5, rate 20/g, material weight 10 g):
      metal material price (rate-driven) = 20 * 0.5 * 10 = 100  (total_metal_invoice_amount)
      total_pricing_fine = weight * purity = 5.0 fine g
      + optional service price 50 → order_amount_total = 150
      total_debit_fine_max (with service) = 150 * 5.0 / 100 = 7.5 fine g
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Metal Coverage Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Test Ring"})
        cls.metal = cls.env["jewelry.metal"].create({"name": "Gold", "code": "AU"})
        cls.alloy = cls.env["jewelry.metal.alloy"].create({
            "name": "Half", "code": "AU500", "metal_id": cls.metal.id, "purity": 0.5,
        })
        cls.rate_at = datetime(2024, 1, 1, 0, 0, 0)
        cls.env["jewelry.metal.rate"].create({
            "metal_id": cls.metal.id,
            "price_per_gram": 20.0,
            "effective_at": datetime(2020, 1, 1, 0, 0, 0),
        })
        revenue = cls.env["account.account"].search([
            ("company_id", "=", cls.env.company.id),
            ("account_type", "=", "income"),
        ], limit=1)
        cls.uom_g = cls.env.ref("uom.product_uom_gram")
        mat_tmpl = cls.env["product.template"].create({
            "name": "Gold Metal", "type": "consu",
            "uom_id": cls.uom_g.id, "uom_po_id": cls.uom_g.id,
            "taxes_id": [(6, 0, [])],
            "repair_material_return_loss_percent": 0.0,  # keep weight_loss = 0 for clean numbers
            "property_account_income_id": revenue.id,
        })
        cls.material_product = mat_tmpl.product_variant_ids[0]
        svc_tmpl = cls.env["product.template"].create({
            "name": "Repair Service", "type": "service", "list_price": 50.0,
            "taxes_id": [(6, 0, [])],
            "property_account_income_id": revenue.id,
        })
        cls.service_product = svc_tmpl.product_variant_ids[0]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _make_order(self, service_price=0.0, material_weight=10.0):
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "state": "delivered",
            "delivery_date": fields.Date.today(),
            "metal_rate_at": self.rate_at,
        })
        # Metal material price is rate-driven: 20 * 0.5 * weight.
        self.env["jewelry.repair.material.line"].create({
            "order_id": order.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": material_weight,
            "alloy_id": self.alloy.id,
            "include_in_invoice": True,
            "consume_from_stock": False,
        })
        if service_price:
            self.env["jewelry.repair.service.line"].create({
                "order_id": order.id,
                "product_id": self.service_product.id,
                "name": "Repair Service",
                "quantity": 1,
                "price_unit": service_price,
            })
        return order

    def _make_account(self, balance_fine=0.0):
        account = self.env["jewelry.client.metal.account"].create({
            "partner_id": self.partner.id,
            "metal_id": self.metal.id,
        })
        if balance_fine:
            self.env["jewelry.client.metal.transaction"].create({
                "account_id": account.id,
                "transaction_type": "deposit_metal",
                "weight_fine": balance_fine,
                "state": "posted",
            })
        return account

    def _billing_line(self, order, account=None):
        batch = self.env["jewelry.repair.billing.batch"].create({
            "partner_id": self.partner.id,
            "client_metal_account_id": account.id if account else False,
        })
        batch.action_select_all_orders()
        return batch, batch.line_ids.filtered(lambda l: l.order_id == order)

    # ── computed metal fields ────────────────────────────────────────────────
    def test_total_pricing_fine(self):
        order = self._make_order()
        _, line = self._billing_line(order)
        self.assertAlmostEqual(line.total_pricing_fine, 5.0, places=4)

    def test_total_metal_invoice_amount(self):
        order = self._make_order()
        _, line = self._billing_line(order)
        self.assertAlmostEqual(line.total_metal_invoice_amount, 100.0, places=2)

    def test_order_amount_total_with_service(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        self.assertAlmostEqual(line.order_amount_total, 150.0, places=2)

    def test_debit_fine_max_metal_only_equals_pricing_fine(self):
        order = self._make_order()
        _, line = self._billing_line(order)
        self.assertAlmostEqual(line.total_debit_fine_max, line.total_pricing_fine, places=4)

    def test_debit_fine_max_with_service(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        self.assertAlmostEqual(line.total_debit_fine_max, 7.5, places=4)

    def test_effective_amount_partial_debit(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        line.client_metal_debit_fine = 2.5  # half of metal pricing fine
        self.assertAlmostEqual(line.metal_amount_reduction, 50.0, places=2)
        self.assertAlmostEqual(line.effective_amount_total, 100.0, places=2)

    def test_action_fill_metal(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        line.action_fill_metal()
        self.assertAlmostEqual(line.client_metal_debit_fine, 5.0, places=4)

    def test_action_fill_full(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        line.action_fill_full()
        self.assertAlmostEqual(line.client_metal_debit_fine, 7.5, places=4)

    def test_debit_exceeds_max_raises(self):
        order = self._make_order(service_price=50.0)
        _, line = self._billing_line(order)
        with self.assertRaises(ValidationError):
            line.client_metal_debit_fine = 8.0  # > 7.5 max

    def test_debit_negative_raises(self):
        order = self._make_order()
        _, line = self._billing_line(order)
        with self.assertRaises(ValidationError):
            line.client_metal_debit_fine = -1.0

    # ── account balance & transactions ───────────────────────────────────────
    def test_account_balance_reflects_posted_transactions(self):
        account = self._make_account(balance_fine=50.0)
        self.assertAlmostEqual(account.balance_fine, 50.0, places=4)

    def test_confirm_posts_debit_transaction(self):
        account = self._make_account(balance_fine=50.0)
        order = self._make_order()
        batch, line = self._billing_line(order, account=account)
        batch.action_fill_all_metal()
        self.assertAlmostEqual(line.client_metal_debit_fine, 5.0, places=4)
        batch.action_confirm()
        tx = self.env["jewelry.client.metal.transaction"].search([
            ("account_id", "=", account.id),
            ("transaction_type", "=", "debit_repair"),
            ("source_res_id", "=", order.id),
        ])
        self.assertEqual(len(tx), 1)
        self.assertAlmostEqual(tx.weight_fine, -5.0, places=4)
        self.assertAlmostEqual(account.balance_fine, 45.0, places=4)

    def test_confirm_requires_account_when_debit(self):
        order = self._make_order()
        batch, line = self._billing_line(order)  # no account
        batch.action_fill_all_metal()
        self.assertGreater(line.client_metal_debit_fine, 0)
        with self.assertRaises(UserError):
            batch.action_confirm()

    def test_cancel_removes_debit_transactions(self):
        account = self._make_account(balance_fine=50.0)
        order = self._make_order()
        batch, _ = self._billing_line(order, account=account)
        batch.action_fill_all_metal()
        batch.action_confirm()
        self.assertAlmostEqual(account.balance_fine, 45.0, places=4)
        batch.action_cancel()
        self.assertAlmostEqual(account.balance_fine, 50.0, places=4)

    # ── invoice reduction ────────────────────────────────────────────────────
    def test_cover_metal_zeroes_material_keeps_service(self):
        account = self._make_account(balance_fine=50.0)
        order = self._make_order(service_price=50.0)
        batch, _ = self._billing_line(order, account=account)
        batch.action_fill_all_metal()  # debit covers metal only
        batch.action_confirm()
        batch.action_create_invoice()
        # Material reduced to 0, service (50) remains.
        self.assertAlmostEqual(batch.invoice_id.amount_total, 50.0, places=2)

    def test_cover_full_skips_order_invoice(self):
        account = self._make_account(balance_fine=50.0)
        order = self._make_order(service_price=50.0)
        batch, line = self._billing_line(order, account=account)
        batch.action_fill_all_full()  # debit covers the full order
        self.assertAlmostEqual(line.effective_amount_total, 0.0, places=2)
        batch.action_confirm()
        # Order is fully covered -> nothing left to invoice.
        with self.assertRaises(UserError):
            batch.action_create_invoice()
