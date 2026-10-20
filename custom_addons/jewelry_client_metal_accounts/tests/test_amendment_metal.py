"""
Tests for the client metal debit during a correction of a delivered order.

client_metal_debit_fine is typed in by hand and the billing lines are recreated
whenever the batch goes back to draft, so the debit has to be carried across the
rollback — and it must not survive unchecked once the order total shrinks.

Fixed numbers (purity 0.5, rate 20/g, material weight 10 g):
  total_pricing_fine        = 10 * 0.5              = 5.0 fine g
  total_metal_invoice_amount = 20 * 0.5 * 10        = 100
  with a 50 service         → order total 150, max  = 150 * 5.0 / 100 = 7.5 fine g
"""
from datetime import datetime

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAmendmentMetalDebit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Metal Debit Client"})
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Metal Debit Ring"})
        cls.metal = cls.env["jewelry.metal"].create({"name": "Debit Gold", "code": "AUD"})
        cls.alloy = cls.env["jewelry.metal.alloy"].create({
            "name": "Debit Half", "code": "AUD500", "metal_id": cls.metal.id, "purity": 0.5,
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
            "name": "Debit Gold Metal", "type": "consu",
            "uom_id": cls.uom_g.id, "uom_po_id": cls.uom_g.id,
            "taxes_id": [(6, 0, [])],
            "repair_material_return_loss_percent": 0.0,
            "property_account_income_id": revenue.id,
        })
        cls.material_product = mat_tmpl.product_variant_ids[0]
        svc_tmpl = cls.env["product.template"].create({
            "name": "Debit Repair Service", "type": "service", "list_price": 50.0,
            "taxes_id": [(6, 0, [])],
            "repair_service_ok": True,
            "property_account_income_id": revenue.id,
        })
        cls.service_product = svc_tmpl.product_variant_ids[0]
        cls.manager = cls.env["res.users"].create({
            "name": "Metal Debit Manager",
            "login": "test_metal_debit_manager",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("jewelry_repair_base.group_jewelry_repair_manager").id,
            ])],
        })

    def _order_with_metal(self, service_price=50.0):
        order = self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "state": "delivered",
            "delivery_date": fields.Date.today(),
            "metal_rate_at": self.rate_at,
        })
        self.env["jewelry.repair.material.line"].create({
            "order_id": order.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": 10.0,
            "alloy_id": self.alloy.id,
            "include_in_invoice": True,
            "consume_from_stock": False,
        })
        self.env["jewelry.repair.service.line"].create({
            "order_id": order.id,
            "product_id": self.service_product.id,
            "name": "Debit Repair Service",
            "quantity": 1,
            "price_unit": service_price,
        })
        return order

    def _account(self, balance_fine=50.0):
        account = self.env["jewelry.client.metal.account"].create({
            "partner_id": self.partner.id,
            "metal_id": self.metal.id,
        })
        self.env["jewelry.client.metal.transaction"].create({
            "account_id": account.id,
            "transaction_type": "deposit_metal",
            "weight_fine": balance_fine,
            "state": "posted",
        })
        return account

    def _confirmed_batch(self, order, account, debit):
        batch = self.env["jewelry.repair.billing.batch"].create({
            "partner_id": self.partner.id,
            "client_metal_account_id": account.id,
        })
        batch.action_select_all_orders()
        batch.line_ids.filtered(lambda l: l.order_id == order).client_metal_debit_fine = debit
        batch.action_confirm()
        return batch

    def _line(self, batch, order):
        return batch.line_ids.filtered(lambda line: line.order_id == order)

    def test_debit_survives_the_rollback(self):
        order = self._order_with_metal()
        account = self._account()
        batch = self._confirmed_batch(order, account, debit=5.0)
        self.assertAlmostEqual(account.balance_fine, 45.0, places=4)

        order.with_user(self.manager)._open_amendment("wrong price")

        self.assertEqual(batch.state, "draft")
        self.assertAlmostEqual(self._line(batch, order).client_metal_debit_fine, 5.0, places=4)
        self.assertAlmostEqual(account.balance_fine, 50.0, places=4,
                               msg="cancelling the batch gives the metal back")

    def test_debit_above_the_new_maximum_blocks_the_rebuild(self):
        order = self._order_with_metal(service_price=50.0)
        account = self._account()
        batch = self._confirmed_batch(order, account, debit=7.5)  # the full order total

        order = order.with_user(self.manager)
        order._open_amendment("service was not performed")
        order.service_line_ids.unlink()  # order total 150 → 100, max 7.5 → 5.0

        self.assertAlmostEqual(self._line(batch, order).total_debit_fine_max, 5.0, places=4)
        with self.assertRaises(UserError):
            batch.action_confirm()

    def test_rebuild_succeeds_once_the_debit_is_corrected(self):
        order = self._order_with_metal(service_price=50.0)
        account = self._account()
        batch = self._confirmed_batch(order, account, debit=7.5)

        order = order.with_user(self.manager)
        order._open_amendment("service was not performed")
        order.service_line_ids.unlink()
        line = self._line(batch, order)
        line.client_metal_debit_fine = line.total_debit_fine_max

        batch.action_confirm()

        self.assertEqual(batch.state, "done")
        self.assertAlmostEqual(account.balance_fine, 45.0, places=4)
        self.assertFalse(order.amendment_open)
