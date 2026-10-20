# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    label_tape_width_mm = fields.Float(
        related="company_id.label_tape_width_mm", readonly=False
    )
    label_length_mm = fields.Float(
        related="company_id.label_length_mm", readonly=False
    )
    label_gap_mm = fields.Float(
        related="company_id.label_gap_mm", readonly=False
    )
    label_print_width_mm = fields.Float(
        related="company_id.label_print_width_mm", readonly=False
    )
    label_density = fields.Integer(
        related="company_id.label_density", readonly=False
    )
    label_dpi = fields.Integer(
        related="company_id.label_dpi", readonly=False
    )
