from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.jewelry_repair_base.models.constants import GEM_CUT_SHAPES, GEM_ORIGIN

STATES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("in_progress", "In Progress"),
    ("shipped", "Shipped"),
    ("received", "Received"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]

# States in which the supplier may still act on the document.
SUPPLIER_OPEN_STATES = ("confirmed", "in_progress")


class JewelryStoneOrder(models.Model):
    _name = "jewelry.stone.order"
    _inherit = ["mail.thread"]
    _description = "Jewelry Stone Order"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        required=True,
        domain=[("is_stone_supplier", "=", True)],
    )
    purpose = fields.Selection(
        [("repair", "For Repair Order"), ("stock", "For Stock")],
        string="Purpose",
        required=True,
        default="repair",
    )
    repair_order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        ondelete="restrict",
        index=True,
    )
    state = fields.Selection(STATES, required=True, default="draft", copy=False, tracking=True)
    stones_payable = fields.Selection(
        [("yes", "Paid to Supplier"), ("no", "Supplier Order — Not Paid")],
        string="Stones Payable",
        required=True,
        default="yes",
        help="Whether we owe the supplier for these stones. Filled in from the repair "
             "order customer when the document is created, then left to the manager.",
    )
    commission_pct = fields.Float(
        string="Commission %",
        digits=(16, 2),
        help="Our share of the price the supplier quotes to the client. Snapshot taken "
             "when the document is created: terms change, past deliveries must not.",
    )
    supplier_waybill = fields.Char(string="Supplier Waybill", copy=False)
    fetched_at = fields.Datetime(
        string="Fetched by Supplier",
        readonly=True,
        copy=False,
        help="When the supplier first read this document. Empty on a confirmed document "
             "means the request never reached them.",
    )
    last_change_at = fields.Datetime(
        string="Last Change",
        readonly=True,
        copy=False,
        help="Watermark the supplier polls on. Not write_date: editing a line leaves the "
             "parent untouched when written directly rather than through the form.",
    )
    shipped_complete = fields.Boolean(
        string="Shipped in Full",
        compute="_compute_shipped_complete",
        store=True,
    )
    request_line_ids = fields.One2many(
        "jewelry.stone.order.request.line", "order_id", string="Requested"
    )
    shipped_line_ids = fields.One2many(
        "jewelry.stone.order.shipped.line", "order_id", string="Shipped"
    )
    return_ids = fields.One2many("jewelry.stone.return", "stone_order_id", string="Returns")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    amount_supplier = fields.Monetary(
        string="Due to Supplier",
        currency_field="currency_id",
        compute="_compute_amount_supplier",
        store=True,
    )
    notes = fields.Text()

    # ── Computed ──

    @api.depends(
        "request_line_ids.quantity",
        "shipped_line_ids.quantity",
        "shipped_line_ids.request_line_id",
    )
    def _compute_shipped_complete(self):
        """Every requested line covered by what actually arrived.

        Inexact for melee on purpose: it ships as a parcel and the supplier may add
        rows with no link back to a request. The supplier is not asked to report
        completeness — see the proposal.
        """
        for order in self:
            shipped_by_request = {}
            for line in order.shipped_line_ids:
                key = line.request_line_id.id
                shipped_by_request[key] = shipped_by_request.get(key, 0) + line.quantity
            order.shipped_complete = all(
                shipped_by_request.get(req.id, 0) >= req.quantity
                for req in order.request_line_ids
            )

    @api.depends(
        "shipped_line_ids.supplier_amount",
        "shipped_line_ids.disposal",
        "stones_payable",
    )
    def _compute_amount_supplier(self):
        for order in self:
            if order.stones_payable != "yes":
                order.amount_supplier = 0.0
                continue
            order.amount_supplier = sum(
                line.supplier_amount
                for line in order.shipped_line_ids
                if line.disposal != "returned"
            )

    # ── Constraints ──

    @api.constrains("purpose", "repair_order_id")
    def _check_repair_order(self):
        for order in self:
            if order.purpose == "repair" and not order.repair_order_id:
                raise ValidationError(_("A stone order for a repair order needs the repair order."))
            if order.purpose == "stock" and order.repair_order_id:
                raise ValidationError(_("A stock stone order cannot point at a repair order."))

    # ── Create ──

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("jewelry.stone.order") or _("New")
            if "stones_payable" not in vals:
                vals["stones_payable"] = self._default_stones_payable(vals)
            if "commission_pct" not in vals and vals.get("supplier_id"):
                supplier = self.env["res.partner"].browse(vals["supplier_id"])
                vals["commission_pct"] = supplier.stone_commission_pct
        return super().create(vals_list)

    @api.model
    def _default_stones_payable(self, vals):
        """The customer of the repair order is the stone supplier → it is their order.

        Works for any supplier, not just API-integrated ones, and degrades correctly for a stock
        order: no repair order means nobody to compare against, so we pay.
        """
        order_id = vals.get("repair_order_id")
        supplier_id = vals.get("supplier_id")
        if not order_id or not supplier_id:
            return "yes"
        repair_order = self.env["jewelry.repair.order"].browse(order_id)
        return "no" if repair_order.partner_id.id == supplier_id else "yes"

    @api.onchange("supplier_id", "repair_order_id")
    def _onchange_supplier_defaults(self):
        """Same rule in the form, so the manager sees the value before saving."""
        if self.state != "draft":
            return
        self.stones_payable = self._default_stones_payable({
            "repair_order_id": self.repair_order_id.id,
            "supplier_id": self.supplier_id.id,
        })
        if self.supplier_id:
            self.commission_pct = self.supplier_id.stone_commission_pct

    # ── Change watermark ──

    def _touch_last_change(self):
        """Mark the document as changed for the supplier's poll.

        Called from state transitions, line writes and return posting. Deliberately
        not called for notes or chatter: the supplier should not be woken by a fixed
        typo.
        """
        self.sudo().write({"last_change_at": fields.Datetime.now()})

    # ── State transitions ──

    def _ensure_state(self, allowed, action):
        for order in self:
            if order.state not in allowed:
                raise UserError(
                    _("%(action)s is not available for %(name)s in state %(state)s.",
                      action=action, name=order.name,
                      state=dict(STATES).get(order.state, order.state))
                )

    def action_confirm(self):
        self._ensure_state(("draft",), _("Confirm"))
        for order in self:
            if not order.request_line_ids:
                raise UserError(_("Nothing to request: the document has no stones."))
        # Origin needs no check here: it is required on the line, so a request without
        # it never reaches this point.
        self.write({"state": "confirmed"})
        self._touch_last_change()

    def action_reset_to_draft(self):
        self._ensure_state(("confirmed",), _("Back to draft"))
        self.write({"state": "draft"})
        self._touch_last_change()

    def action_set_in_progress(self):
        """The supplier took the request into work.

        Available by hand too: a supplier without an integration is driven by the
        manager, and the document has to work without any API at all.
        """
        self._ensure_state(("confirmed",), _("Take into work"))
        self.write({"state": "in_progress"})
        self._touch_last_change()

    def action_mark_shipped(self):
        """Straight from Confirmed is allowed — In Progress is optional."""
        self._ensure_state(SUPPLIER_OPEN_STATES, _("Mark as shipped"))
        self.write({"state": "shipped"})
        self._touch_last_change()

    def action_open_reject_wizard(self):
        self.ensure_one()
        self._ensure_state(SUPPLIER_OPEN_STATES, _("Reject"))
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject Stone Order"),
            "res_model": "jewelry.stone.order.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_reject(self, comment):
        """Rejection always carries a reason — that is the whole value of the record."""
        if not (comment or "").strip():
            raise UserError(_("Say why the stones cannot be supplied."))
        self._ensure_state(SUPPLIER_OPEN_STATES, _("Reject"))
        self.write({"state": "rejected"})
        for order in self:
            order.message_post(body=_("Rejected by the supplier: %s", comment))
        self._touch_last_change()

    def action_receive(self):
        self._ensure_state(("shipped",), _("Receive"))
        self.write({"state": "received"})
        self._touch_last_change()

    def action_cancel(self):
        self._ensure_state(("draft", "confirmed", "in_progress"), _("Cancel"))
        self.write({"state": "cancelled"})
        self._touch_last_change()

    # ── Transfer into the repair order ──

    def _transferable_lines(self):
        """Received stones that are still on hand and not yet in the repair order."""
        self.ensure_one()
        return self.shipped_line_ids.filtered(lambda line: not line.disposal)

    def _transfer_targets(self):
        """Pair each shipped line with the gem line it feeds, if it already has one."""
        self.ensure_one()
        existing = self.env["jewelry.repair.gem.line"].search([
            ("order_id", "=", self.repair_order_id.id),
            ("stone_order_line_id", "in", self._transferable_lines().ids),
        ])
        return {gem.stone_order_line_id.id: gem for gem in existing}

    def _transfer_preview(self):
        """What the transfer would do, without doing it."""
        self.ensure_one()
        targets = self._transfer_targets()
        preview = []
        for line in self._transferable_lines():
            label = line.gem_type_id.name or _("Stone")
            if line.certificate_ref:
                label = "%s · %s" % (label, line.certificate_ref)
            detail = _("%(qty)s pc, %(ct).4f ct", qty=line.quantity, ct=line.weight_ct)
            preview.append({
                "action": "update" if targets.get(line.id) else "create",
                "description": label,
                "detail": detail,
            })
        skipped = self.shipped_line_ids - self._transferable_lines()
        for line in skipped:
            preview.append({
                "action": "skip",
                "description": line.gem_type_id.name or _("Stone"),
                "detail": dict(line._fields["disposal"].selection).get(line.disposal, ""),
            })
        return preview

    def _transfer_apply(self):
        """Copy received stones into the repair order's Stones tab.

        Certified stones expand one to one — a gem line holds a single certificate —
        while melee updates the line it already fed. Prices stay behind until base and
        margin exist on gem lines; see the proposal.
        """
        self.ensure_one()
        if self.state != "received":
            raise UserError(_("Transfer the stones once they are received."))
        if not self.repair_order_id:
            raise UserError(_("A stock stone order has no repair order to transfer into."))
        targets = self._transfer_targets()
        GemLine = self.env["jewelry.repair.gem.line"]
        for line in self._transferable_lines():
            values = {
                "gem_type_id": line.gem_type_id.id,
                "origin": line.origin,
                "cut_shape": line.cut_shape,
                "standard_size_id": line.standard_size_id.id,
                "quantity": line.quantity,
                "weight_ct": line.weight_ct,
            }
            existing = targets.get(line.id)
            if existing:
                existing.write(values)
                continue
            values.update({
                "order_id": self.repair_order_id.id,
                "stone_order_line_id": line.id,
                "certificate_id": line._find_or_create_certificate().id,
            })
            GemLine.create(values)

    def action_open_transfer_wizard(self):
        self.ensure_one()
        if self.state != "received":
            raise UserError(_("Transfer the stones once they are received."))
        if not self.repair_order_id:
            raise UserError(_("A stock stone order has no repair order to transfer into."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Transfer Stones Into the Order"),
            "res_model": "jewelry.stone.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_request_remainder(self):
        """Open a fresh draft for what did not arrive."""
        self.ensure_one()
        self._ensure_state(("received",), _("Request the remainder"))
        shipped_by_request = {}
        for line in self.shipped_line_ids:
            key = line.request_line_id.id
            shipped_by_request[key] = shipped_by_request.get(key, 0) + line.quantity
        missing = []
        for req in self.request_line_ids:
            short = req.quantity - shipped_by_request.get(req.id, 0)
            if short > 0:
                missing.append((0, 0, req._copy_values(short)))
        if not missing:
            raise UserError(_("Everything requested has arrived."))
        remainder = self.create({
            "supplier_id": self.supplier_id.id,
            "purpose": self.purpose,
            "repair_order_id": self.repair_order_id.id,
            "stones_payable": self.stones_payable,
            "commission_pct": self.commission_pct,
            "request_line_ids": missing,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.stone.order",
            "res_id": remainder.id,
            "view_mode": "form",
        }


class JewelryStoneOrderLineMixin(models.AbstractModel):
    _name = "jewelry.stone.order.line.mixin"
    _description = "Jewelry Stone Order Line Mixin"

    # Fields whose change the supplier has to learn about. Everything else is ours.
    TRACKED_FIELDS = {
        "gem_type_id", "origin", "cut_shape", "standard_size_id",
        "quantity", "weight_ct", "certificate_ref",
    }

    order_id = fields.Many2one(
        "jewelry.stone.order", string="Stone Order", required=True, ondelete="cascade"
    )
    gem_type_id = fields.Many2one("jewelry.gem.type", string="Gem Type", required=True)
    origin = fields.Selection(GEM_ORIGIN, string="Origin")
    cut_shape = fields.Selection(GEM_CUT_SHAPES, string="Cut Shape")
    standard_size_id = fields.Many2one(
        "jewelry.gem.standard.size",
        string="Size",
        domain="[('gem_type_id', '=', gem_type_id), ('cut_shape', '=', cut_shape)]",
    )
    quantity = fields.Integer(string="Qty", required=True, default=1)
    weight_ct = fields.Float(string="Weight/pc (ct)", digits=(16, 4))
    certificate_ref = fields.Char(string="Certificate No.")

    @api.constrains("certificate_ref", "quantity")
    def _check_certificate_single_stone(self):
        """A certificate always covers one stone.

        Without this, twelve stones would travel under one number and never
        reconcile with the supplier.
        """
        for line in self:
            if line.certificate_ref and line.quantity != 1:
                raise ValidationError(
                    _("Certificate %s covers a single stone, so the quantity has to be 1.",
                      line.certificate_ref)
                )

    @api.constrains("standard_size_id", "gem_type_id")
    def _check_size_matches_type(self):
        for line in self:
            size = line.standard_size_id
            if size and size.gem_type_id != line.gem_type_id:
                raise ValidationError(_("The size belongs to a different gem type."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped("order_id")._touch_last_change()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if self.TRACKED_FIELDS & set(vals):
            self.mapped("order_id")._touch_last_change()
        return res

    def unlink(self):
        orders = self.mapped("order_id")
        res = super().unlink()
        orders.exists()._touch_last_change()
        return res


class JewelryStoneOrderRequestLine(models.Model):
    _name = "jewelry.stone.order.request.line"
    _inherit = "jewelry.stone.order.line.mixin"
    _description = "Jewelry Stone Order Request Line"
    _order = "id"

    origin = fields.Selection(GEM_ORIGIN, string="Origin", required=True)
    total_weight_ct = fields.Float(
        string="Total (ct)", compute="_compute_total_weight_ct", store=True, digits=(16, 4)
    )

    @api.depends("quantity", "weight_ct")
    def _compute_total_weight_ct(self):
        for line in self:
            line.total_weight_ct = line.quantity * line.weight_ct

    @api.onchange("standard_size_id")
    def _onchange_standard_size_id(self):
        if self.standard_size_id:
            self.weight_ct = self.standard_size_id.weight_ct

    def _check_order_editable(self):
        """The requested composition is frozen once the document is confirmed.

        Otherwise the warehouse picks against one list while we look at another.
        """
        for line in self:
            if line.order_id.state != "draft":
                raise UserError(_(
                    "%s is confirmed — the requested stones cannot be changed. "
                    "Take it back to draft, or cancel it and make a new one.",
                    line.order_id.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_order_editable()
        return lines

    def write(self, vals):
        self._check_order_editable()
        return super().write(vals)

    def unlink(self):
        self._check_order_editable()
        return super().unlink()

    def _copy_values(self, quantity):
        """Values for the same requirement in a smaller quantity."""
        self.ensure_one()
        return {
            "gem_type_id": self.gem_type_id.id,
            "origin": self.origin,
            "cut_shape": self.cut_shape,
            "standard_size_id": self.standard_size_id.id,
            "quantity": quantity,
            "weight_ct": self.weight_ct,
        }


class JewelryStoneOrderShippedLine(models.Model):
    _name = "jewelry.stone.order.shipped.line"
    _inherit = "jewelry.stone.order.line.mixin"
    _description = "Jewelry Stone Order Shipped Line"
    _order = "id"

    request_line_id = fields.Many2one(
        "jewelry.stone.order.request.line",
        string="Requested Line",
        ondelete="set null",
        help="Optional: the warehouse may ship something that was never requested.",
    )
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    price_unit = fields.Monetary(
        string="Client Price/pc",
        currency_field="currency_id",
        help="What the supplier quotes to the end client.",
    )
    subtotal = fields.Monetary(
        string="Client Amount",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    supplier_amount = fields.Monetary(
        string="Due to Supplier",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Client amount less our commission.",
    )
    disposal = fields.Selection(
        [("returned", "Returned to Supplier"), ("broken", "Broken")],
        string="Disposal",
        copy=False,
    )
    broken_charge_to = fields.Selection(
        [("workshop", "Workshop"), ("client", "Client"), ("supplier", "Supplier")],
        string="Charged To",
        copy=False,
        help="Who carries a broken stone. No rule — the manager decides case by case.",
    )

    @api.depends("quantity", "price_unit", "order_id.commission_pct")
    def _compute_amounts(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
            line.supplier_amount = line.subtotal * (1 - (line.order_id.commission_pct or 0.0) / 100.0)

    @api.constrains("disposal", "broken_charge_to")
    def _check_broken_charge(self):
        for line in self:
            if line.disposal == "broken" and not line.broken_charge_to:
                raise ValidationError(_("Say who carries the broken stone."))

    def _find_or_create_certificate(self):
        """Match the supplier's certificate number to a record, or open a stub.

        The supplier may send only the number; the manager fills the rest in from the
        paper later. Numbers are unique per lab, so matching on the number is enough.
        """
        self.ensure_one()
        if not self.certificate_ref:
            return self.env["jewelry.gem.certificate"]
        Certificate = self.env["jewelry.gem.certificate"]
        existing = Certificate.search([("name", "=", self.certificate_ref)], limit=1)
        if existing:
            return existing
        return Certificate.create({
            "name": self.certificate_ref,
            "gem_type_id": self.gem_type_id.id,
            "carat_weight": self.weight_ct,
            "origin": self.origin,
        })
