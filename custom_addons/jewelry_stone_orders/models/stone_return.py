from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryStoneReturn(models.Model):
    _name = "jewelry.stone.return"
    _inherit = ["mail.thread"]
    _description = "Jewelry Stone Return"
    _order = "return_date desc, id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    stone_order_id = fields.Many2one(
        "jewelry.stone.order",
        string="Stone Order",
        required=True,
        ondelete="restrict",
        domain=[("state", "=", "received")],
    )
    supplier_id = fields.Many2one(related="stone_order_id.supplier_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="stone_order_id.currency_id", readonly=True)
    return_date = fields.Date(required=True, default=fields.Date.context_today)
    waybill = fields.Char(string="Our Waybill", copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")], required=True, default="draft", copy=False
    )
    line_ids = fields.One2many("jewelry.stone.return.line", "return_id", string="Lines")
    amount_total = fields.Monetary(
        string="Returned Amount",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )
    notes = fields.Text()

    @api.depends("line_ids.shipped_line_id.supplier_amount")
    def _compute_amount_total(self):
        for doc in self:
            doc.amount_total = sum(doc.line_ids.mapped("shipped_line_id.supplier_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("jewelry.stone.return") or _("New")
        return super().create(vals_list)

    def action_post(self):
        for doc in self:
            if doc.state != "draft":
                raise UserError(_("%s is already posted.", doc.name))
            if not doc.line_ids:
                raise UserError(_("Nothing to return."))
            doc.line_ids.mapped("shipped_line_id").write({"disposal": "returned"})
            doc.state = "done"
            doc.stone_order_id._touch_last_change()
            doc.stone_order_id.message_post(
                body=_("Stones returned by %(name)s, waybill %(waybill)s.",
                       name=doc.name, waybill=doc.waybill or "—")
            )

    def action_reset_to_draft(self):
        for doc in self:
            if doc.state != "done":
                continue
            doc.line_ids.mapped("shipped_line_id").write({"disposal": False})
            doc.state = "draft"
            doc.stone_order_id._touch_last_change()


class JewelryStoneReturnLine(models.Model):
    _name = "jewelry.stone.return.line"
    _description = "Jewelry Stone Return Line"
    _order = "id"

    return_id = fields.Many2one(
        "jewelry.stone.return", string="Return", required=True, ondelete="cascade"
    )
    shipped_line_id = fields.Many2one(
        "jewelry.stone.order.shipped.line",
        string="Received Stone",
        required=True,
        ondelete="restrict",
    )
    gem_type_id = fields.Many2one(related="shipped_line_id.gem_type_id", readonly=True)
    certificate_ref = fields.Char(related="shipped_line_id.certificate_ref", readonly=True)
    quantity = fields.Integer(related="shipped_line_id.quantity", readonly=True)
    weight_ct = fields.Float(related="shipped_line_id.weight_ct", readonly=True)

    @api.constrains("shipped_line_id", "return_id")
    def _check_line_belongs_to_order(self):
        for line in self:
            if line.shipped_line_id.order_id != line.return_id.stone_order_id:
                raise ValidationError(_("The stone does not belong to the stone order being returned."))
