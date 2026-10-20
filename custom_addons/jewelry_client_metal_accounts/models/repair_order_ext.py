from odoo import api, fields, models


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    client_metal_account_ids = fields.Many2many(
        "jewelry.client.metal.account",
        string="Client Metal Accounts",
        compute="_compute_client_metal_account_ids",
    )

    @api.depends("partner_id")
    def _compute_client_metal_account_ids(self):
        MetalAccount = self.env["jewelry.client.metal.account"]
        for order in self:
            if order.partner_id:
                accounts = MetalAccount.search([
                    ("partner_id", "=", order.partner_id.id),
                    ("active", "=", True),
                ])
                order.client_metal_account_ids = accounts
            else:
                order.client_metal_account_ids = MetalAccount
