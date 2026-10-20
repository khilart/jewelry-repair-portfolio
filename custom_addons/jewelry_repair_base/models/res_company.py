# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    invoice_contact_id = fields.Many2one(
        "res.partner",
        string="Invoice Contact Person",
        help="Person to contact printed on the order invoice. "
             "Pick an existing contact (e.g. a child contact of this company).",
    )
    invoice_payment_term_days = fields.Integer(
        string="Invoice Payment Term (days)",
        default=30,
    )
    invoice_payment_qr = fields.Image(string="Invoice Payment QR Code")
