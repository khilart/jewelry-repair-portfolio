from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime, timedelta


@tagged("post_install", "-at_install")
class TestMetalAccountingBase(TransactionCase):
    """Base class with shared fixtures for all metal accounting tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # --- Master data ---
        cls.gold = cls.env["jewelry.metal"].create({"name": "Gold", "code": "AU"})
        cls.silver = cls.env["jewelry.metal"].create({"name": "Silver", "code": "AG"})

        cls.alloy_585 = cls.env["jewelry.metal.alloy"].create(
            {"name": "Gold 585", "code": "AU585", "metal_id": cls.gold.id, "purity": 0.585}
        )
        cls.alloy_750 = cls.env["jewelry.metal.alloy"].create(
            {"name": "Gold 750", "code": "AU750", "metal_id": cls.gold.id, "purity": 0.750}
        )
        cls.alloy_silver = cls.env["jewelry.metal.alloy"].create(
            {"name": "Silver 925", "code": "AG925", "metal_id": cls.silver.id, "purity": 0.925}
        )

        cls.storage_main = cls.env["jewelry.metal.storage"].create(
            {"name": "Main Storage", "code": "MAIN"}
        )
        cls.storage_workshop = cls.env["jewelry.metal.storage"].create(
            {"name": "Workshop", "code": "WS"}
        )

        cls.partner = cls.env["res.partner"].create({"name": "Gold Supplier"})

        cls.rate_datetime = datetime(2024, 1, 15, 12, 0, 0)
        cls.gold_rate = cls.env["jewelry.metal.rate"].create(
            {
                "metal_id": cls.gold.id,
                "price_per_gram": 5000.0,
                "effective_at": cls.rate_datetime - timedelta(hours=1),
                "company_id": cls.env.company.id,
            }
        )

    def _make_receipt(self, alloy, weight, dest_storage=None, partner=None, rate_datetime=None):
        """Helper: create and return a receipt document (draft)."""
        dest_storage = dest_storage or self.storage_main
        partner = partner or self.partner
        rate_datetime = rate_datetime or self.rate_datetime
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "receipt",
                "dest_storage_id": dest_storage.id,
                "partner_id": partner.id,
                "document_date": rate_datetime,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "alloy_id": alloy.id,
                            "weight": weight,
                            "rate_datetime": rate_datetime,
                        },
                    )
                ],
            }
        )
        return doc

    def _make_writeoff(self, alloy, weight, source_storage=None):
        """Helper: create and return a write-off document (draft)."""
        source_storage = source_storage or self.storage_main
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "writeoff",
                "source_storage_id": source_storage.id,
                "line_ids": [
                    (0, 0, {"alloy_id": alloy.id, "weight": weight})
                ],
            }
        )
        return doc

    def _make_transfer(self, alloy, weight, source_storage=None, dest_storage=None):
        """Helper: create and return a transfer document (draft)."""
        source_storage = source_storage or self.storage_main
        dest_storage = dest_storage or self.storage_workshop
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "source_storage_id": source_storage.id,
                "dest_storage_id": dest_storage.id,
                "line_ids": [
                    (0, 0, {"alloy_id": alloy.id, "weight": weight})
                ],
            }
        )
        return doc

    def _get_balance(self, alloy, storage):
        return self.env["jewelry.metal.move"]._get_balance(alloy, storage)


@tagged("post_install", "-at_install")
class TestMetalStorageConstraints(TestMetalAccountingBase):
    """Storage master data and constraints."""

    def test_unique_code_per_company(self):
        """Duplicate storage code within the same company must raise."""
        with self.assertRaises(Exception):
            self.env["jewelry.metal.storage"].create(
                {"name": "Duplicate", "code": "MAIN"}
            )

    def test_different_company_same_code_allowed(self):
        """Same code is allowed for a different company."""
        other_company = self.env["res.company"].create({"name": "Other Co"})
        storage = self.env["jewelry.metal.storage"].create(
            {"name": "Other Main", "code": "MAIN", "company_id": other_company.id}
        )
        self.assertTrue(storage.id)


@tagged("post_install", "-at_install")
class TestMetalDocumentReceipt(TestMetalAccountingBase):
    """Receipt operation: state machine and balance changes."""

    def test_receipt_post_creates_moves(self):
        doc = self._make_receipt(self.alloy_585, weight=10.0)
        self.assertEqual(doc.state, "draft")
        doc.action_post()
        self.assertEqual(doc.state, "posted")
        self.assertTrue(doc.move_ids)

    def test_receipt_increases_balance(self):
        doc = self._make_receipt(self.alloy_585, weight=10.0)
        doc.action_post()
        balance = self._get_balance(self.alloy_585, self.storage_main)
        self.assertAlmostEqual(balance, 10.0, places=3)

    def test_receipt_accumulates_balance(self):
        self._make_receipt(self.alloy_585, weight=10.0).action_post()
        self._make_receipt(self.alloy_585, weight=5.0).action_post()
        balance = self._get_balance(self.alloy_585, self.storage_main)
        self.assertAlmostEqual(balance, 15.0, places=3)

    def test_different_alloys_tracked_separately(self):
        self._make_receipt(self.alloy_585, weight=10.0).action_post()
        self._make_receipt(self.alloy_750, weight=7.0).action_post()
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 10.0, places=3)
        self.assertAlmostEqual(self._get_balance(self.alloy_750, self.storage_main), 7.0, places=3)

    def test_receipt_requires_partner(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "receipt",
                "dest_storage_id": self.storage_main.id,
                "document_date": self.rate_datetime,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 5.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_receipt_requires_dest_storage(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "receipt",
                "partner_id": self.partner.id,
                "document_date": self.rate_datetime,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 5.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_receipt_requires_lines(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "receipt",
                "dest_storage_id": self.storage_main.id,
                "partner_id": self.partner.id,
                "document_date": self.rate_datetime,
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()


@tagged("post_install", "-at_install")
class TestMetalDocumentWriteoff(TestMetalAccountingBase):
    """Write-off operation: balance decreases, validation."""

    def setUp(self):
        super().setUp()
        # Pre-fill storage with 20g
        self._make_receipt(self.alloy_585, weight=20.0).action_post()

    def test_writeoff_decreases_balance(self):
        self._make_writeoff(self.alloy_585, weight=8.0).action_post()
        balance = self._get_balance(self.alloy_585, self.storage_main)
        self.assertAlmostEqual(balance, 12.0, places=3)

    def test_writeoff_requires_source_storage(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "writeoff",
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 5.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_writeoff_weight_zero_raises(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "writeoff",
                "source_storage_id": self.storage_main.id,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 0.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()


@tagged("post_install", "-at_install")
class TestMetalDocumentTransfer(TestMetalAccountingBase):
    """Transfer operation: source decreases, dest increases."""

    def setUp(self):
        super().setUp()
        self._make_receipt(self.alloy_585, weight=20.0, dest_storage=self.storage_main).action_post()

    def test_transfer_moves_weight_between_storages(self):
        self._make_transfer(self.alloy_585, weight=6.0).action_post()
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 14.0, places=3)
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_workshop), 6.0, places=3)

    def test_transfer_requires_both_storages(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "source_storage_id": self.storage_main.id,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 5.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_transfer_same_storage_raises(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_main.id,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 5.0})],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_fill_from_source_storage_creates_lines_for_positive_balances(self):
        self._make_receipt(self.alloy_750, weight=4.0, dest_storage=self.storage_main).action_post()
        writeoff = self._make_writeoff(self.alloy_585, weight=2.0, source_storage=self.storage_main)
        writeoff.document_date = self.rate_datetime
        writeoff.action_post()
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "document_date": self.rate_datetime,
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_workshop.id,
            }
        )

        doc.action_fill_from_source_storage()

        self.assertEqual(len(doc.line_ids), 2)
        weights_by_alloy = {line.alloy_id.id: line.weight for line in doc.line_ids}
        self.assertAlmostEqual(weights_by_alloy[self.alloy_585.id], 18.0, places=3)
        self.assertAlmostEqual(weights_by_alloy[self.alloy_750.id], 4.0, places=3)

    def test_fill_from_source_storage_replaces_existing_lines(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "document_date": self.rate_datetime,
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_workshop.id,
                "line_ids": [(0, 0, {"alloy_id": self.alloy_585.id, "weight": 1.0})],
            }
        )

        doc.action_fill_from_source_storage()

        self.assertEqual(len(doc.line_ids), 1)
        self.assertAlmostEqual(doc.line_ids.weight, 20.0, places=3)

    def test_fill_from_source_storage_requires_source_storage(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "document_date": self.rate_datetime,
                "dest_storage_id": self.storage_workshop.id,
            }
        )

        with self.assertRaises(UserError):
            doc.action_fill_from_source_storage()

    def test_fill_from_source_storage_requires_positive_balances(self):
        empty_storage = self.env["jewelry.metal.storage"].create({"name": "Empty", "code": "EMPTY"})
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "transfer",
                "document_date": self.rate_datetime,
                "source_storage_id": empty_storage.id,
                "dest_storage_id": self.storage_workshop.id,
            }
        )

        with self.assertRaises(UserError):
            doc.action_fill_from_source_storage()

    def test_fill_writeoff_from_source_storage_zeroes_balance_on_date(self):
        overdraft = self._make_writeoff(self.alloy_750, weight=3.0, source_storage=self.storage_main)
        overdraft.document_date = self.rate_datetime
        overdraft.action_post()
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "writeoff",
                "document_date": self.rate_datetime,
                "source_storage_id": self.storage_main.id,
                "partner_id": self.partner.id,
            }
        )

        doc.action_fill_from_source_storage()

        self.assertEqual(doc.operation_type, "mixed")
        lines_by_alloy = {line.alloy_id: line for line in doc.line_ids}
        self.assertEqual(lines_by_alloy[self.alloy_585].operation_type, "writeoff")
        self.assertAlmostEqual(lines_by_alloy[self.alloy_585].weight, 20.0, places=3)
        self.assertEqual(lines_by_alloy[self.alloy_750].operation_type, "receipt")
        self.assertAlmostEqual(lines_by_alloy[self.alloy_750].weight, 3.0, places=3)

        doc.action_post()

        move_model = self.env["jewelry.metal.move"]
        for alloy in (self.alloy_585, self.alloy_750):
            self.assertAlmostEqual(
                move_model._get_balance(alloy, self.storage_main, at_datetime=self.rate_datetime), 0.0, places=3
            )


@tagged("post_install", "-at_install")
class TestMetalDocumentRemelt(TestMetalAccountingBase):
    """Remelt operation: input alloy OUT, output alloy IN."""

    def setUp(self):
        super().setUp()
        self._make_receipt(self.alloy_585, weight=20.0, dest_storage=self.storage_main).action_post()

    def test_remelt_converts_alloy(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "remelt",
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_workshop.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "alloy_id": self.alloy_585.id,
                            "weight": 10.0,
                            "output_alloy_id": self.alloy_750.id,
                            "output_weight": 7.8,
                        },
                    )
                ],
            }
        )
        doc.action_post()
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 10.0, places=3)
        self.assertAlmostEqual(self._get_balance(self.alloy_750, self.storage_workshop), 7.8, places=3)

    def test_remelt_requires_output_alloy(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "remelt",
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_workshop.id,
                "line_ids": [
                    (0, 0, {"alloy_id": self.alloy_585.id, "weight": 10.0, "output_weight": 7.8})
                ],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()

    def test_remelt_requires_output_weight_positive(self):
        doc = self.env["jewelry.metal.document"].create(
            {
                "operation_type": "remelt",
                "source_storage_id": self.storage_main.id,
                "dest_storage_id": self.storage_workshop.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "alloy_id": self.alloy_585.id,
                            "weight": 10.0,
                            "output_alloy_id": self.alloy_750.id,
                            "output_weight": 0.0,
                        },
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            doc.action_post()


@tagged("post_install", "-at_install")
class TestMetalDocumentStateTransitions(TestMetalAccountingBase):
    """State machine: draft → posted → cancel → draft."""

    def test_cancel_draft_document(self):
        doc = self._make_receipt(self.alloy_585, weight=5.0)
        doc.action_cancel()
        self.assertEqual(doc.state, "cancel")
        self.assertFalse(doc.move_ids)

    def test_cancel_posted_document_marks_moves_cancelled(self):
        doc = self._make_receipt(self.alloy_585, weight=5.0)
        doc.action_post()
        self.assertTrue(doc.move_ids)
        doc.action_cancel()
        self.assertEqual(doc.state, "cancel")
        self.assertTrue(all(m.state == "cancel" for m in doc.move_ids))

    def test_cancel_posted_removes_from_balance(self):
        doc = self._make_receipt(self.alloy_585, weight=10.0)
        doc.action_post()
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 10.0, places=3)
        doc.action_cancel()
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 0.0, places=3)

    def test_reset_to_draft_from_cancel(self):
        doc = self._make_receipt(self.alloy_585, weight=5.0)
        doc.action_cancel()
        doc.action_reset_to_draft()
        self.assertEqual(doc.state, "draft")
        self.assertFalse(doc.move_ids)

    def test_cannot_reset_posted_to_draft_directly(self):
        doc = self._make_receipt(self.alloy_585, weight=5.0)
        doc.action_post()
        with self.assertRaises(UserError):
            doc.action_reset_to_draft()

    def test_repost_after_reset_to_draft(self):
        doc = self._make_receipt(self.alloy_585, weight=5.0)
        doc.action_post()
        doc.action_cancel()
        doc.action_reset_to_draft()
        doc.action_post()
        self.assertEqual(doc.state, "posted")
        self.assertAlmostEqual(self._get_balance(self.alloy_585, self.storage_main), 5.0, places=3)


@tagged("post_install", "-at_install")
class TestMetalBalance(TestMetalAccountingBase):
    """_get_balance: accuracy, at_datetime filtering, missing args."""

    def test_balance_zero_with_no_moves(self):
        balance = self._get_balance(self.alloy_585, self.storage_main)
        self.assertEqual(balance, 0.0)

    def test_balance_at_datetime_excludes_future_moves(self):
        past = datetime(2024, 1, 10, 0, 0, 0)
        future = datetime(2024, 1, 20, 0, 0, 0)

        past_rate = self.env["jewelry.metal.rate"].create(
            {
                "metal_id": self.gold.id,
                "price_per_gram": 5000.0,
                "effective_at": past - timedelta(hours=1),
                "company_id": self.env.company.id,
            }
        )

        doc_past = self._make_receipt(self.alloy_585, weight=10.0, rate_datetime=past)
        doc_past.document_date = past
        doc_past.action_post()

        doc_future = self._make_receipt(self.alloy_585, weight=5.0, rate_datetime=future)
        doc_future.document_date = future
        doc_future.action_post()

        balance_at_past = self.env["jewelry.metal.move"]._get_balance(
            self.alloy_585, self.storage_main, at_datetime=past
        )
        self.assertAlmostEqual(balance_at_past, 10.0, places=3)

        balance_total = self._get_balance(self.alloy_585, self.storage_main)
        self.assertAlmostEqual(balance_total, 15.0, places=3)

    def test_balance_returns_zero_without_alloy(self):
        balance = self.env["jewelry.metal.move"]._get_balance(
            self.env["jewelry.metal.alloy"].browse(), self.storage_main
        )
        self.assertEqual(balance, 0.0)

    def test_balance_returns_zero_without_storage(self):
        balance = self.env["jewelry.metal.move"]._get_balance(
            self.alloy_585, self.env["jewelry.metal.storage"].browse()
        )
        self.assertEqual(balance, 0.0)


@tagged("post_install", "-at_install")
class TestReceiptPricing(TestMetalAccountingBase):
    """Receipt line pricing: rate lookup and amount calculation."""

    def test_amount_calculated_on_receipt_create(self):
        doc = self._make_receipt(self.alloy_585, weight=10.0)
        line = doc.line_ids[0]
        # amount = price_per_gram * purity * weight = 5000 * 0.585 * 10
        expected = 5000.0 * 0.585 * 10.0
        self.assertAlmostEqual(line.amount, expected, places=2)
        self.assertAlmostEqual(line.rate_price_per_gram, 5000.0, places=2)

    def test_no_rate_found_gives_zero_amount(self):
        # Date before any rate
        early_date = datetime(2020, 1, 1, 0, 0, 0)
        doc = self._make_receipt(self.alloy_585, weight=10.0, rate_datetime=early_date)
        line = doc.line_ids[0]
        self.assertEqual(line.amount, 0.0)
        self.assertEqual(line.rate_price_per_gram, 0.0)

    def test_writeoff_line_has_no_pricing(self):
        self._make_receipt(self.alloy_585, weight=20.0).action_post()
        doc = self._make_writeoff(self.alloy_585, weight=5.0)
        line = doc.line_ids[0]
        self.assertEqual(line.amount, 0.0)
        self.assertEqual(line.rate_price_per_gram, 0.0)

    def test_newer_rate_takes_priority(self):
        newer_rate = self.env["jewelry.metal.rate"].create(
            {
                "metal_id": self.gold.id,
                "price_per_gram": 6000.0,
                "effective_at": self.rate_datetime,
                "company_id": self.env.company.id,
            }
        )
        doc = self._make_receipt(
            self.alloy_585, weight=10.0, rate_datetime=self.rate_datetime + timedelta(minutes=1)
        )
        line = doc.line_ids[0]
        expected = 6000.0 * 0.585 * 10.0
        self.assertAlmostEqual(line.amount, expected, places=2)


@tagged("post_install", "-at_install")
class TestMetalStockStatementWizard(TestMetalAccountingBase):
    """Period statement for opening, turnover, and closing balances."""

    def test_stock_statement_calculates_opening_turnover_and_closing(self):
        receipt_open = self._make_receipt(self.alloy_585, weight=10.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 10, 10, 0, 0))
        receipt_open.document_date = datetime(2024, 1, 10, 10, 0, 0)
        receipt_open.action_post()

        writeoff_open = self._make_writeoff(self.alloy_585, weight=3.0, source_storage=self.storage_main)
        writeoff_open.document_date = datetime(2024, 1, 15, 10, 0, 0)
        writeoff_open.action_post()

        receipt_period = self._make_receipt(self.alloy_585, weight=5.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 25, 10, 0, 0))
        receipt_period.document_date = datetime(2024, 1, 25, 10, 0, 0)
        receipt_period.action_post()

        transfer_period = self._make_transfer(self.alloy_585, weight=2.0, source_storage=self.storage_main, dest_storage=self.storage_workshop)
        transfer_period.document_date = datetime(2024, 1, 28, 10, 0, 0)
        transfer_period.action_post()

        wizard = self.env["jewelry.metal.stock.statement.wizard"].create(
            {
                "date_from": date(2024, 1, 20),
                "date_to": date(2024, 1, 31),
            }
        )

        wizard.action_build_statement()

        main_lines = wizard.line_ids.filtered(lambda line: line.storage_id == self.storage_main)
        workshop_lines = wizard.line_ids.filtered(lambda line: line.storage_id == self.storage_workshop)

        self.assertEqual(len(wizard.line_ids), 2)
        self.assertAlmostEqual(sum(main_lines.mapped("opening_balance")), 7.0, places=3)
        self.assertAlmostEqual(sum(main_lines.mapped("weight_in")), 5.0, places=3)
        self.assertAlmostEqual(sum(main_lines.mapped("weight_out")), 2.0, places=3)
        self.assertAlmostEqual(sum(main_lines.mapped("closing_balance")), 10.0, places=3)

        self.assertAlmostEqual(sum(workshop_lines.mapped("opening_balance")), 0.0, places=3)
        self.assertAlmostEqual(sum(workshop_lines.mapped("weight_in")), 2.0, places=3)
        self.assertAlmostEqual(sum(workshop_lines.mapped("weight_out")), 0.0, places=3)
        self.assertAlmostEqual(sum(workshop_lines.mapped("closing_balance")), 2.0, places=3)

    def test_stock_statement_respects_storage_and_alloy_filters(self):
        receipt_gold = self._make_receipt(self.alloy_585, weight=6.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 20, 10, 0, 0))
        receipt_gold.document_date = datetime(2024, 1, 20, 10, 0, 0)
        receipt_gold.action_post()

        receipt_silver = self._make_receipt(self.alloy_silver, weight=4.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 21, 10, 0, 0))
        receipt_silver.document_date = datetime(2024, 1, 21, 10, 0, 0)
        receipt_silver.action_post()

        wizard = self.env["jewelry.metal.stock.statement.wizard"].create(
            {
                "date_from": date(2024, 1, 1),
                "date_to": date(2024, 1, 31),
                "storage_ids": [(6, 0, self.storage_main.ids)],
                "alloy_ids": [(6, 0, self.alloy_585.ids)],
            }
        )

        wizard.action_build_statement()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.storage_id, self.storage_main)
        self.assertEqual(wizard.line_ids.alloy_id, self.alloy_585)
        self.assertAlmostEqual(wizard.line_ids.opening_balance, 0.0, places=3)
        self.assertAlmostEqual(wizard.line_ids.weight_in, 6.0, places=3)
        self.assertAlmostEqual(wizard.line_ids.weight_out, 0.0, places=3)
        self.assertAlmostEqual(wizard.line_ids.closing_balance, 6.0, places=3)

    def test_stock_statement_skips_zero_lines_by_default(self):
        receipt = self._make_receipt(self.alloy_585, weight=5.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 5, 10, 0, 0))
        receipt.document_date = datetime(2024, 1, 5, 10, 0, 0)
        receipt.action_post()

        writeoff = self._make_writeoff(self.alloy_585, weight=5.0, source_storage=self.storage_main)
        writeoff.document_date = datetime(2024, 1, 10, 10, 0, 0)
        writeoff.action_post()

        wizard = self.env["jewelry.metal.stock.statement.wizard"].create(
            {
                "date_from": date(2024, 1, 20),
                "date_to": date(2024, 1, 31),
            }
        )

        wizard.action_build_statement()

        self.assertFalse(wizard.line_ids)

    def test_stock_statement_can_include_zero_lines(self):
        receipt = self._make_receipt(self.alloy_585, weight=5.0, dest_storage=self.storage_main, rate_datetime=datetime(2024, 1, 5, 10, 0, 0))
        receipt.document_date = datetime(2024, 1, 5, 10, 0, 0)
        receipt.action_post()

        writeoff = self._make_writeoff(self.alloy_585, weight=5.0, source_storage=self.storage_main)
        writeoff.document_date = datetime(2024, 1, 10, 10, 0, 0)
        writeoff.action_post()

        wizard = self.env["jewelry.metal.stock.statement.wizard"].create(
            {
                "date_from": date(2024, 1, 20),
                "date_to": date(2024, 1, 31),
                "include_zero_lines": True,
            }
        )

        wizard.action_build_statement()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertAlmostEqual(sum(wizard.line_ids.mapped("opening_balance")), 0.0, places=3)
        self.assertAlmostEqual(sum(wizard.line_ids.mapped("closing_balance")), 0.0, places=3)
