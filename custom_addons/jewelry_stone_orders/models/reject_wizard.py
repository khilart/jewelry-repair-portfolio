from odoo import fields, models


class JewelryStoneOrderRejectWizard(models.TransientModel):
    _name = "jewelry.stone.order.reject.wizard"
    _description = "Reject a Stone Order"

    order_id = fields.Many2one("jewelry.stone.order", required=True, ondelete="cascade")
    comment = fields.Text(string="Reason", required=True)

    def action_reject(self):
        self.ensure_one()
        self.order_id.action_reject(self.comment)
        return {"type": "ir.actions.act_window_close"}
