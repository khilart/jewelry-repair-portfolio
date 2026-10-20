# -*- coding: utf-8 -*-

import io
import re

from PIL import Image

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrderLabel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Test Jeweller", "customer_rank": 1}
        )
        cls.item_type = cls.env["jewelry.repair.item.type"].create({"name": "Ring"})
        cls.order = cls.env["jewelry.repair.order"].create(
            {
                "partner_id": cls.partner.id,
                "item_type_id": cls.item_type.id,
                "quantity": 2,
            }
        )

    def test_geometry_matches_settings(self):
        """Defaults reproduce the geometry the stock printer app uses."""
        geometry = self.order._label_geometry()
        self.assertEqual(geometry["width_dots"], 96)
        self.assertEqual(geometry["width_bytes"], 12)
        self.assertEqual(geometry["height_dots"], 264)

    def test_geometry_follows_label_length(self):
        self.env.company.label_length_mm = 50.0
        geometry = self.order._label_geometry()
        self.assertEqual(geometry["height_dots"], 384)

    def test_png_has_printable_size(self):
        image = Image.open(io.BytesIO(self.order.label_png()))
        geometry = self.order._label_geometry()
        self.assertEqual(image.size, (geometry["height_dots"], geometry["width_dots"]))
        self.assertEqual(image.mode, "1")

    def test_tspl_structure(self):
        program = self.order.label_tspl()
        geometry = self.order._label_geometry()
        header = re.match(
            rb"SIZE 14\.0 mm,35\.0 mm\r\n"
            rb"GAP 8\.0 mm,0 mm\r\n"
            rb"DIRECTION 0,0\r\n"
            rb"DENSITY 4\r\n"
            rb"CLS\r\n"
            rb"BITMAP 0,8,(\d+),(\d+),1,",
            program,
        )
        self.assertTrue(header, "TSPL header does not match the expected commands")
        width_bytes, height = int(header.group(1)), int(header.group(2))
        self.assertEqual(width_bytes, geometry["width_bytes"])
        self.assertEqual(height, geometry["height_dots"])

        raster = program[header.end():-len(b"\r\nPRINT 1\r\n")]
        self.assertEqual(len(raster), width_bytes * height)
        self.assertTrue(program.endswith(b"\r\nPRINT 1\r\n"))

    def test_tspl_bits_are_inverted(self):
        """TSPL prints a zero bit, so a mostly white label is mostly ones."""
        program = self.order.label_tspl()
        raster = program[program.index(b",1,") + 3:-len(b"\r\nPRINT 1\r\n")]
        ones = sum(bin(byte).count("1") for byte in raster)
        self.assertGreater(ones, len(raster) * 8 * 0.7)

    def test_printed_number_is_the_tail(self):
        """People read the last digits; the QR keeps the whole number."""
        self.order.name = "RO2026-0342"
        self.assertEqual(self.order._label_number_text(), "0342")

    def test_lines_carry_the_agreed_content(self):
        alloy = self.env["jewelry.metal.alloy"].search([], limit=1)
        if alloy:
            self.order.alloy_id = alloy
        values = self.order._label_text_values()
        self.assertEqual(values[0], self.partner.display_name)
        self.assertIn("Ring", values[1])
        self.assertIn("x2", values[1], "quantity above one belongs on the label")
        self.assertTrue(
            any(re.fullmatch(r"\d{2}\.\d{2} \d{2}:\d{2}", value) for value in values),
            "the deadline should read as day and time, without the year",
        )
        if alloy:
            self.assertIn(alloy.display_name, values)

    def test_fonts_fit_the_tape(self):
        """Everything has to fit across the tape, whatever the label length."""
        height = self.order._label_geometry()["width_dots"]
        for line_count in range(1, 7):
            number, body = self.order._label_fonts(height, line_count)
            used = number + 2 + line_count * (body + 2)
            self.assertLessEqual(used, height, "%d lines overflow the tape" % line_count)

    def test_long_customer_name_is_truncated(self):
        self.partner.name = "Очень Длинное Название Ювелирного Клиента с Продолжением"
        self.assertTrue(self.order.label_png())

    def test_renders_without_customer(self):
        """Optional label content must not break rendering."""
        order = self.env["jewelry.repair.order"].new({"name": "RO2026-0001"})
        geometry = order._label_geometry()
        image = order._render_label_image()
        self.assertEqual(image.size, (geometry["height_dots"], geometry["width_dots"]))
