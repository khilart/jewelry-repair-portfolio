from odoo.tests import tagged
from odoo.exceptions import UserError

from .test_metal_accounting import TestMetalAccountingBase


@tagged("post_install", "-at_install")
class TestOrderMetalDocuments(TestMetalAccountingBase):
    """metal.document synchronisation from a repair order's material lines.

    Safety net for _sync_metal_documents / action_sync_metal_documents
    (the live "Calculate Metal" / manager-accept flow) — currently defined
    on the base order model but logically belonging to metal accounting.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Ring"})
        cls.uom_g = cls.env.ref("uom.product_uom_gram")
        tmpl = cls.env["product.template"].create({
            "name": "Gold Metal", "type": "consu",
            "uom_id": cls.uom_g.id, "uom_po_id": cls.uom_g.id,
        })
        cls.material_product = tmpl.product_variant_ids[0]
        # Pre-fill main storage so writeoffs can post.
        prefill = cls.env["jewelry.metal.document"].create({
            "operation_type": "receipt",
            "dest_storage_id": cls.storage_main.id,
            "partner_id": cls.partner.id,
            "document_date": cls.rate_datetime,
            "line_ids": [(0, 0, {
                "alloy_id": cls.alloy_585.id, "weight": 1000.0,
                "rate_datetime": cls.rate_datetime,
            })],
        })
        prefill.action_post()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _make_order(self):
        return self.env["jewelry.repair.order"].create({
            "partner_id": self.partner.id,
            "item_type_id": self.item_type.id,
            "metal_rate_at": self.rate_datetime,
        })

    def _add_material(self, order, weight=5.0, consume=True, source_storage=None,
                      return_to=False, return_storage=None):
        return self.env["jewelry.repair.material.line"].create({
            "order_id": order.id,
            "product_id": self.material_product.id,
            "uom_id": self.uom_g.id,
            "quantity": 1,
            "weight": weight,
            "alloy_id": self.alloy_585.id,
            "include_in_invoice": True,
            "consume_from_stock": consume,
            "source_storage_id": source_storage.id if source_storage else False,
            "return_to_storage": return_to,
            "return_storage_id": return_storage.id if return_storage else False,
        })

    def _document_of(self, order):
        return self.env["jewelry.metal.document"].search([("repair_order_id", "=", order.id)])

    # ── writeoff ─────────────────────────────────────────────────────────────
    def test_sync_creates_posted_writeoff(self):
        order = self._make_order()
        self._add_material(order, weight=5.0, source_storage=self.storage_main)
        order._sync_metal_documents()
        doc = self._document_of(order)
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc.state, "posted")
        self.assertEqual(len(doc.line_ids), 1)
        self.assertEqual(doc.line_ids.operation_type, "writeoff")
        self.assertEqual(doc.line_ids.source_storage_id, self.storage_main)
        self.assertAlmostEqual(doc.line_ids.weight, 5.0, places=3)

    def test_sync_requires_source_storage(self):
        order = self._make_order()
        self._add_material(order, weight=5.0, source_storage=False)
        with self.assertRaises(UserError):
            order._sync_metal_documents()

    # ── return to storage (receipt) ──────────────────────────────────────────
    def test_sync_creates_receipt_for_return(self):
        order = self._make_order()
        self._add_material(
            order, weight=3.0, consume=False,
            return_to=True, return_storage=self.storage_workshop,
        )
        order._sync_metal_documents()
        doc = self._document_of(order)
        self.assertEqual(len(doc.line_ids), 1)
        self.assertEqual(doc.line_ids.operation_type, "receipt")
        self.assertEqual(doc.line_ids.dest_storage_id, self.storage_workshop)

    def test_sync_requires_return_storage(self):
        order = self._make_order()
        self._add_material(
            order, weight=3.0, consume=False,
            return_to=True, return_storage=False,
        )
        with self.assertRaises(UserError):
            order._sync_metal_documents()

    # ── no metal lines / lifecycle ───────────────────────────────────────────
    def test_no_document_without_metal_lines(self):
        order = self._make_order()  # no material lines at all
        order._sync_metal_documents()
        self.assertFalse(self._document_of(order))

    def test_cancel_removes_metal_document(self):
        order = self._make_order()
        self._add_material(order, weight=5.0, source_storage=self.storage_main)
        order._sync_metal_documents()
        self.assertTrue(self._document_of(order))
        order.action_cancel()
        self.assertFalse(self._document_of(order))
        self.assertEqual(order.state, "cancel")
