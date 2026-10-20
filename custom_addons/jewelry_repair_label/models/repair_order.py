# -*- coding: utf-8 -*-
"""Order label for narrow thermal label printers.

The printer has no driver: it takes a bitmap inside a TSPL command, so the label
is rendered as a 1-bit image rather than a PDF. The print head is narrow and the
label runs lengthwise, so the design is drawn horizontally the way a person reads
it and rotated by 90 degrees when it is packed into TSPL.
"""

import io

import qrcode
from PIL import Image, ImageDraw, ImageFont

from odoo import _, models
from odoo.tools import format_datetime

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = FONT_DIR + "/DejaVuSans-Bold.ttf"
FONT_REGULAR = FONT_DIR + "/DejaVuSans.ttf"

# Unprinted margin at both ends of the label, in dots.
MARGIN_DOTS = 8
# Space between the QR block and the text column, in dots.
TEXT_GAP_DOTS = 6

# Tail of the order number printed in large type. The full number stays in the
# QR code, so a short tail is enough for a person to read.
NUMBER_TAIL = 4

NUMBER_FONT_MAX = 28
NUMBER_FONT_MIN = 14
BODY_FONT_MAX = 16
BODY_FONT_MIN = 9
LINE_SPACING = 2


def _fit_font(path, text, max_width, max_size, min_size):
    """Largest size at which the text still fits on one line."""
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(path, size)
        if font.getlength(text) <= max_width:
            return font
    return ImageFont.truetype(path, min_size)


def _ellipsize_to_fit(font, text, max_width):
    """Text as it is, or cut with an ellipsis when it overruns the label."""
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]
    return text + "…"


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    def _label_geometry(self):
        """Label size in printer dots.

        The bitmap width is given to TSPL in bytes, so it is rounded to a
        multiple of eight.
        """
        company = self.env.company
        dots_per_mm = company.label_dpi / 25.4
        width_dots = int(round(company.label_print_width_mm * dots_per_mm)) // 8 * 8
        length_dots = int(round(company.label_length_mm * dots_per_mm))
        return {
            "width_dots": max(width_dots, 8),
            "height_dots": max(length_dots - 2 * MARGIN_DOTS, 8),
            "width_bytes": max(width_dots // 8, 1),
        }

    def _label_qr_image(self, target_dots):
        """QR sized so that every module is a whole number of dots."""

        def build(box_size):
            code = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=box_size,
                border=4,
            )
            code.add_data(self.name)
            code.make(fit=True)
            return code

        probe = build(1)
        modules = probe.modules_count + 2 * probe.border
        return build(max(1, target_dots // modules)).make_image().convert("1")

    def _label_number_text(self):
        """Significant tail of the order number, the part people say out loud."""
        return (self.name or "")[-NUMBER_TAIL:]

    def _label_text_values(self):
        """Data lines, in the order they matter when the item is picked up."""
        values = []
        if self.partner_id:
            values.append(self.partner_id.display_name)

        item = []
        if self.item_type_id:
            item.append(self.item_type_id.display_name)
        if self.item_size_id:
            item.append(self.item_size_id.display_name)
        if self.quantity > 1:
            item.append("x%s" % self.quantity)
        if item:
            values.append(" ".join(item))

        if self.alloy_id:
            values.append(self.alloy_id.display_name)
        if self.deadline_date:
            # Day and time, no year: the label lives days, and the hour matters
            # when several orders are due the same day.
            values.append(format_datetime(
                self.env, self.deadline_date, dt_format="dd.MM HH:mm"
            ))
        return values

    def _label_fonts(self, height, line_count):
        """Largest type at which the number and every data line fit the tape.

        The tape width is the limit here: a longer label widens the columns but
        gives no extra room for lines, so the fonts have to give way instead.
        """
        for body in range(BODY_FONT_MAX, BODY_FONT_MIN - 1, -1):
            for number in range(NUMBER_FONT_MAX, NUMBER_FONT_MIN - 1, -1):
                if number + 2 + line_count * (body + LINE_SPACING) <= height:
                    return number, body
        return NUMBER_FONT_MIN, BODY_FONT_MIN

    def _render_label_image(self):
        """The label as a person reads it: QR on the left, text on the right."""
        self.ensure_one()
        geometry = self._label_geometry()
        width, height = geometry["height_dots"], geometry["width_dots"]

        canvas = Image.new("1", (width, height), 1)
        draw = ImageDraw.Draw(canvas)

        qr = self._label_qr_image(height)
        canvas.paste(qr, (0, (height - qr.size[1]) // 2))

        left = qr.size[0] + TEXT_GAP_DOTS
        text_width = width - left

        values = self._label_text_values()
        number_size, body_size = self._label_fonts(height, len(values))

        number = self._label_number_text()
        number_font = _fit_font(
            FONT_BOLD, number, text_width, number_size, NUMBER_FONT_MIN
        )
        draw.text((left, 0), number, font=number_font, fill=0)

        # Bold throughout: thin type disappears on cheap thermal paper.
        body = ImageFont.truetype(FONT_BOLD, body_size)
        cursor = number_font.size + 2
        for value in values:
            if cursor + body_size > height:
                break
            draw.text((left, cursor), _ellipsize_to_fit(body, value, text_width), font=body, fill=0)
            cursor += body_size + LINE_SPACING
        return canvas

    def label_png(self):
        """Label as a 1-bit PNG, for preview and for printing by hand."""
        buffer = io.BytesIO()
        self._render_label_image().save(buffer, format="PNG")
        return buffer.getvalue()

    def label_tspl(self):
        """Ready to send TSPL program: header, bitmap, print command.

        TSPL treats a zero bit as a black dot, the opposite of the rendered
        image, so the bits are inverted here.
        """
        self.ensure_one()
        company = self.env.company
        geometry = self._label_geometry()
        rotated = self._render_label_image().transpose(Image.ROTATE_90)
        pixels = rotated.load()

        raster = bytearray()
        for row in range(rotated.height):
            for byte_index in range(geometry["width_bytes"]):
                byte = 0
                for bit in range(8):
                    if pixels[byte_index * 8 + bit, row]:  # white pixel
                        byte |= 1 << (7 - bit)
                raster.append(byte)

        header = (
            "SIZE %.1f mm,%.1f mm\r\n"
            "GAP %.1f mm,0 mm\r\n"
            "DIRECTION 0,0\r\n"
            "DENSITY %d\r\n"
            "CLS\r\n"
            "BITMAP 0,%d,%d,%d,1,"
        ) % (
            company.label_tape_width_mm,
            company.label_length_mm,
            company.label_gap_mm,
            company.label_density,
            MARGIN_DOTS,
            geometry["width_bytes"],
            rotated.height,
        )
        return header.encode("ascii") + bytes(raster) + b"\r\nPRINT 1\r\n"

    def action_print_label(self):
        """Opens the print dialog, which talks to the printer from the browser."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "jewelry_repair_label.print",
            "name": _("Print Label"),
            "target": "new",
            "params": {"order_id": self.id, "order_name": self.name},
        }
