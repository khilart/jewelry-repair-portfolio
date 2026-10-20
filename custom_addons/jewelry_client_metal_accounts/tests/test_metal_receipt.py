from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMetalReceiptAdjustment(TransactionCase):
    """Adjustment receipt: fine weight from alloy weight × purity, posted with its own sign."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Metal Client"})
        cls.metal = cls.env["jewelry.metal"].create({"name": "Gold", "code": "AU"})
        cls.alloy = cls.env["jewelry.metal.alloy"].create({
            "name": "Three Quarters", "code": "AU750", "metal_id": cls.metal.id, "purity": 0.75,
        })
        cls.account = cls.env["jewelry.client.metal.account"].create({
            "partner_id": cls.partner.id,
            "metal_id": cls.metal.id,
        })

    def _adjustment(self, weight_alloy):
        form = Form(self.env["jewelry.client.metal.receipt"])
        form.operation_type = "adjustment"
        form.partner_id = self.partner
        form.account_id = self.account
        with form.line_ids.new() as line:
            line.alloy_id = self.alloy
            line.weight_alloy = weight_alloy
        return form.save()

    def test_fine_weight_is_computed(self):
        receipt = self._adjustment(4.0)
        self.assertAlmostEqual(receipt.line_ids.weight_fine, 3.0, places=4)

    def test_alloy_weight_is_computed_from_fine(self):
        form = Form(self.env["jewelry.client.metal.receipt"])
        form.operation_type = "adjustment"
        form.partner_id = self.partner
        form.account_id = self.account
        with form.line_ids.new() as line:
            line.alloy_id = self.alloy
            line.weight_fine = 3.0
        receipt = form.save()
        self.assertAlmostEqual(receipt.line_ids.weight_alloy, 4.0, places=3)

    def test_negative_adjustment_lowers_the_balance(self):
        self._adjustment(8.0).action_post()
        self._adjustment(-4.0).action_post()
        self.assertAlmostEqual(self.account.balance_fine, 3.0, places=4)
