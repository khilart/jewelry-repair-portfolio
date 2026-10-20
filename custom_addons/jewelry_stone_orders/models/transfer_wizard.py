from odoo import _, api, fields, models
from odoo.exceptions import UserError


class JewelryStoneTransferWizard(models.TransientModel):
    _name = "jewelry.stone.transfer.wizard"
    _description = "Transfer Received Stones Into the Repair Order"

    order_id = fields.Many2one("jewelry.stone.order", required=True, ondelete="cascade")
    repair_order_id = fields.Many2one(related="order_id.repair_order_id", readonly=True)
    line_ids = fields.One2many(
        "jewelry.stone.transfer.wizard.line", "wizard_id", string="Preview"
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        order = self.env["jewelry.stone.order"].browse(vals.get("order_id") or self.env.context.get("default_order_id"))
        if order:
            vals["line_ids"] = [(0, 0, preview) for preview in order._transfer_preview()]
        return vals

    def action_apply(self):
        self.ensure_one()
        self.order_id._transfer_apply()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.order",
            "res_id": self.repair_order_id.id,
            "view_mode": "form",
        }


class JewelryStoneTransferWizardLine(models.TransientModel):
    _name = "jewelry.stone.transfer.wizard.line"
    _description = "Transfer Preview Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "jewelry.stone.transfer.wizard", required=True, ondelete="cascade"
    )
    action = fields.Selection(
        [("create", "Will be added"), ("update", "Will be updated"), ("skip", "Left alone")],
        string="Action",
        readonly=True,
    )
    description = fields.Char(readonly=True)
    detail = fields.Char(readonly=True)
