# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    label_tape_width_mm = fields.Float(
        string="Label Tape Width (mm)",
        default=14.0,
        help="Physical width of the label tape. Goes into the SIZE command.",
    )
    label_length_mm = fields.Float(
        string="Label Length (mm)",
        default=35.0,
        help="Length of a single label along the feed direction.",
    )
    label_gap_mm = fields.Float(
        string="Label Gap (mm)",
        default=8.0,
        help="Gap between die-cut labels on the roll, used by the printer to find "
             "the next label. Set it to 0 for continuous tape: with a gap set, the "
             "printer keeps feeding blank tape looking for one that is not there.",
    )
    label_print_width_mm = fields.Float(
        string="Printable Width (mm)",
        default=12.0,
        help="Width the print head actually covers. Smaller than the tape width, "
             "which leaves an unprinted edge on both sides.",
    )
    label_density = fields.Integer(
        string="Print Density",
        default=4,
        help="Heat setting of the print head, 1 to 15. Higher is darker.",
    )
    label_dpi = fields.Integer(
        string="Printer Resolution (dpi)",
        default=203,
        help="Print head resolution. Used to convert millimetres into dots.",
    )
