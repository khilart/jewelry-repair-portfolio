from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class JewelryRepairBillingLine(models.Model):
    _name = "jewelry.repair.billing.line"
    _description = "Jewelry Repair Billing Line"
    _order = "order_delivery_date, id"

    batch_id = fields.Many2one(
        "jewelry.repair.billing.batch",
        string="Billing Batch",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Include", default=False)
    order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        required=True,
        ondelete="cascade",
    )
    order_name = fields.Char(related="order_id.name", string="Order No.", readonly=True)
    order_item_type_id = fields.Many2one(related="order_id.item_type_id", string="Item Type", readonly=True)
    order_delivery_date = fields.Date(related="order_id.delivery_date", string="Delivery Date", readonly=True, store=True)
    order_amount_total = fields.Monetary(
        related="order_id.amount_total",
        string="Total",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)

    _sql_constraints = [
        ("billing_line_order_unique", "unique(batch_id, order_id)", "Each order can appear only once in a billing batch."),
    ]

    def action_open_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.order",
            "res_id": self.order_id.id,
            "view_mode": "form",
            "target": "new",
        }


class JewelryRepairBillingBatch(models.Model):
    _name = "jewelry.repair.billing.batch"
    _inherit = ["mail.thread"]
    _description = "Jewelry Repair Billing Batch"
    _order = "date_to desc, id desc"

    name = fields.Char(
        string="Batch Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    date_from = fields.Date()
    date_to = fields.Date()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    order_ids = fields.Many2many(
        "jewelry.repair.order",
        "jewelry_repair_billing_batch_order_rel",
        "batch_id",
        "order_id",
        string="Orders",
    )
    line_ids = fields.One2many(
        "jewelry.repair.billing.line",
        "batch_id",
        string="Billing Lines",
    )
    order_count = fields.Integer(compute="_compute_order_count")
    amount_total = fields.Float(compute="_compute_amount_total", string="Total Amount")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        domain=[("move_type", "=", "out_invoice")],
        copy=False,
    )
    invoice_payment_state = fields.Selection(
        related="invoice_id.payment_state",
        string="Invoice Payment",
        readonly=True,
    )
    amendment_order_ids = fields.One2many(
        "jewelry.repair.order",
        "amendment_billing_batch_id",
        string="Orders Being Corrected",
    )
    rebuild_pending = fields.Boolean(
        string="Waiting For Rebuild",
        compute="_compute_rebuild_pending",
        store=True,
        help="This batch was rolled back to correct an order and has not been confirmed again.",
    )

    delivery_ids = fields.Many2many(
        "jewelry.repair.delivery",
        string="Deliveries",
        compute="_compute_delivery_ids",
    )
    delivery_count = fields.Integer(compute="_compute_delivery_ids")
    payment_count = fields.Integer(compute="_compute_payment_count")

    @api.depends("amendment_order_ids")
    def _compute_rebuild_pending(self):
        for batch in self:
            batch.rebuild_pending = bool(batch.amendment_order_ids)

    @api.depends("line_ids.order_id.delivery_id")
    def _compute_delivery_ids(self):
        """There is no direct batch-to-delivery link: it is derived through the orders."""
        for batch in self:
            deliveries = batch.line_ids.order_id.delivery_id
            batch.delivery_ids = deliveries
            batch.delivery_count = len(deliveries)

    @api.depends("invoice_id")
    def _compute_payment_count(self):
        for batch in self:
            batch.payment_count = len(batch._get_invoice_payments())

    def _get_invoice_payments(self):
        """Payments reconciled against the invoice of this batch.

        sudo: reading account.move is not part of the repair roles.
        """
        self.ensure_one()
        invoice = self.invoice_id.sudo()
        return invoice._get_reconciled_payments() if invoice else invoice.browse()

    def action_open_deliveries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliveries"),
            "res_model": "jewelry.repair.delivery",
            "domain": [("id", "in", self.delivery_ids.ids)],
            "view_mode": "tree,form",
        }

    def action_open_payments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Payments"),
            "res_model": "account.payment",
            "domain": [("id", "in", self._get_invoice_payments().ids)],
            "view_mode": "tree,form",
        }
    invoice_reference = fields.Char(
        related="invoice_id.name",
        string="Invoice Reference",
        readonly=True,
    )
    notes = fields.Text()
    last_billing_date_to = fields.Date(
        compute="_compute_last_billing_info",
        string="Last Billing Period End",
    )

    @api.depends("partner_id")
    def _compute_last_billing_info(self):
        for batch in self:
            if not batch.partner_id:
                batch.last_billing_date_to = False
                continue
            last = self.search(
                [
                    ("partner_id", "=", batch.partner_id.id),
                    ("state", "=", "done"),
                    ("id", "!=", batch._origin.id or 0),
                ],
                order="date_to desc",
                limit=1,
            )
            batch.last_billing_date_to = last.date_to if last else False

    @api.depends("partner_id")
    def _compute_currency_id(self):
        for batch in self:
            batch.currency_id = self.env.company.currency_id

    @api.depends("order_ids")
    def _compute_order_count(self):
        for batch in self:
            batch.order_count = len(batch.order_ids)

    @api.depends(
        "order_ids.service_line_ids.subtotal",
        "order_ids.material_line_ids.subtotal",
        "order_ids.material_line_ids.include_in_invoice",
        "order_ids.gem_line_ids.subtotal",
        "order_ids.gem_line_ids.include_in_invoice",
    )
    def _compute_amount_total(self):
        for batch in self:
            batch.amount_total = (
                sum(batch.order_ids.mapped("service_line_ids.subtotal"))
                + sum(batch.order_ids.mapped("material_line_ids").filtered("include_in_invoice").mapped("subtotal"))
                + sum(batch.order_ids.mapped("gem_line_ids").filtered("include_in_invoice").mapped("subtotal"))
            )

    def _get_candidate_orders(self):
        self.ensure_one()
        if not self.partner_id:
            return self.env["jewelry.repair.order"]
        return self.env["jewelry.repair.order"].search(
            [
                ("partner_id", "=", self.partner_id.id),
                ("state", "=", "delivered"),
                ("billing_batch_id", "=", False),
            ],
            order="delivery_date, id",
        )

    def _sync_candidate_lines(self):
        for batch in self:
            if batch.state != "draft":
                continue
            if not batch.partner_id:
                batch.line_ids = [(5, 0, 0)]
                batch.order_ids = [(5, 0, 0)]
                continue
            candidate_orders = batch._get_candidate_orders()
            selected_order_ids = set(batch.order_ids.ids) & set(candidate_orders.ids)
            commands = [(5, 0, 0)]
            for order in candidate_orders:
                commands.append((0, 0, {
                    "order_id": order.id,
                    "selected": order.id in selected_order_ids,
                }))
            batch.line_ids = commands
            batch.order_ids = [(6, 0, list(selected_order_ids))]

    def _sync_order_ids_from_selected_lines(self):
        for batch in self:
            selected_orders = batch.line_ids.filtered(
                lambda l: l.selected and l.order_id
            ).mapped("order_id")
            batch.order_ids = [(6, 0, selected_orders.ids)]

    def write(self, vals):
        if self.env.user.has_group("jewelry_repair_base.group_jewelry_repair_director"):
            raise UserError(_("Directors have read-only access. Contact a manager to make changes."))
        result = super().write(vals)
        if "line_ids" in vals:
            self.filtered(lambda b: b.state == "draft")._sync_order_ids_from_selected_lines()
        if {"partner_id", "state"} & set(vals):
            self.filtered(lambda b: b.state == "draft")._sync_candidate_lines()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = sequence.next_by_code("jewelry.repair.billing.batch") or _("New")
        batches = super().create(vals_list)
        batches.filtered("partner_id")._sync_candidate_lines()
        return batches

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for batch in self:
            if not batch.partner_id:
                batch.line_ids = [(5, 0, 0)]
                batch.order_ids = [(5, 0, 0)]
                batch.date_from = False
                batch.date_to = False
                continue
            batch._sync_candidate_lines()
            last = self.search(
                [("partner_id", "=", batch.partner_id.id), ("state", "=", "done")],
                order="date_to desc",
                limit=1,
            )
            if last:
                batch.date_from = last.date_to + relativedelta(days=1)
            else:
                first_order = self.env["jewelry.repair.order"].search(
                    [
                        ("partner_id", "=", batch.partner_id.id),
                        ("state", "=", "delivered"),
                        ("billing_batch_id", "=", False),
                        ("delivery_date", "!=", False),
                    ],
                    order="delivery_date asc",
                    limit=1,
                )
                batch.date_from = first_order.delivery_date if first_order else False
            batch.date_to = fields.Date.context_today(batch)

    @api.onchange("line_ids", "line_ids.selected")
    def _onchange_line_ids(self):
        self._sync_order_ids_from_selected_lines()

    def action_select_all_orders(self):
        for batch in self.filtered(lambda b: b.state == "draft"):
            batch.line_ids.write({"selected": True})
            batch._sync_order_ids_from_selected_lines()

    def action_select_by_period(self):
        for batch in self.filtered(lambda b: b.state == "draft"):
            if not batch.date_from or not batch.date_to:
                raise UserError(_("Set the period dates before selecting orders by period."))
            for line in batch.line_ids:
                line.selected = bool(
                    line.order_delivery_date
                    and batch.date_from <= line.order_delivery_date <= batch.date_to
                )
            batch._sync_order_ids_from_selected_lines()

    def action_clear_selected_orders(self):
        for batch in self.filtered(lambda b: b.state == "draft"):
            batch.line_ids.write({"selected": False})
            batch._sync_order_ids_from_selected_lines()

    def action_print_billing(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/jewelry_repair_billing.report_jewelry_repair_billing_document/%s" % self.id,
            "target": "new",
        }

    def _get_billing_service_summary(self):
        self.ensure_one()
        return self.order_ids._jewelry_service_summary()

    def _get_billing_material_summary(self):
        self.ensure_one()
        return self.order_ids._jewelry_material_summary()

    def action_confirm(self):
        for batch in self:
            if not batch.order_ids:
                raise UserError(_("Add at least one delivered order before confirming the billing batch."))

            already_billed = batch.order_ids.filtered(
                lambda o: o.billing_batch_id and o.billing_batch_id != batch
            )
            if already_billed:
                lines = "\n".join(
                    "  • %s → %s" % (o.name, o.billing_batch_id.name)
                    for o in already_billed
                )
                raise UserError(
                    _("The following orders are already included in another billing batch:\n%s") % lines
                )

            wrong_orders = batch.order_ids.filtered(
                lambda o: o.partner_id != batch.partner_id or o.state != "delivered"
            )
            if wrong_orders:
                lines = "\n".join("  • %s" % o.name for o in wrong_orders)
                raise UserError(
                    _("The following orders do not match the customer or are not in delivered state:\n%s") % lines
                )

            batch.order_ids.write({"billing_batch_id": batch.id, "billing_date": fields.Date.context_today(batch)})
            batch.line_ids.filtered(lambda l: not l.selected).unlink()
            batch.state = "done"
            batch._post_billing_client_metal_transactions()
            batch.order_ids.filtered("amendment_open")._close_amendment()

    def _post_billing_client_metal_transactions(self):
        pass

    def _should_skip_invoice_for_order(self, order):
        return False

    def _get_service_line_invoice_price_unit(self, line):
        return line.price_unit

    def _get_gem_line_invoice_price_unit(self, line):
        return line.price_unit

    def action_create_invoice(self):
        for batch in self:
            if batch.state != "done":
                raise UserError(_("Confirm the billing batch before creating an invoice."))
            if batch.invoice_id:
                raise UserError(_("An invoice is already linked to this billing batch."))
            if not batch.order_ids:
                raise UserError(_("The billing batch does not contain any orders."))

            invoice_line_vals = []
            for order in batch.order_ids.sorted(lambda order: (order.delivery_date or fields.Date.today(), order.id)):
                if batch._should_skip_invoice_for_order(order):
                    continue
                for line in order.service_line_ids:
                    account = (
                        line.product_id.property_account_income_id
                        or line.product_id.categ_id.property_account_income_categ_id
                    )
                    if not account:
                        raise UserError(
                            _(
                                "Set an income account on the service product or its category before creating the invoice."
                            )
                        )

                    invoice_line_vals.append(
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "name": f"{order.name} - {line.name}",
                                "quantity": line.total_quantity,
                                "price_unit": batch._get_service_line_invoice_price_unit(line),
                                "account_id": account.id,
                                "tax_ids": [(6, 0, line.product_id.taxes_id.filtered(
                                    lambda tax: tax.company_id == self.env.company
                                ).ids)],
                            },
                        )
                    )

                for line in order.material_line_ids.filtered("include_in_invoice"):
                    account = (
                        line.product_id.property_account_income_id
                        or line.product_id.categ_id.property_account_income_categ_id
                    )
                    if not account:
                        raise UserError(
                            _(
                                "Set an income account on the material product or its category before creating the invoice."
                            )
                        )

                    invoice_line_vals.append(
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "name": f"{order.name} - {line.description or line.product_id.display_name}",
                                "quantity": line.quantity,
                                "price_unit": self._get_material_line_invoice_price_unit(line),
                                "account_id": account.id,
                                "tax_ids": [(6, 0, line.product_id.taxes_id.filtered(
                                    lambda tax: tax.company_id == self.env.company
                                ).ids)],
                            },
                        )
                    )

                for line in order.gem_line_ids.filtered("include_in_invoice"):
                    if not line.product_id:
                        continue
                    account = (
                        line.product_id.property_account_income_id
                        or line.product_id.categ_id.property_account_income_categ_id
                    )
                    if not account:
                        raise UserError(
                            _(
                                "Set an income account on the stone product or its category before creating the invoice."
                            )
                        )
                    invoice_line_vals.append(
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "name": f"{order.name} - {line.gem_type_id.name}",
                                "quantity": line.quantity,
                                "price_unit": batch._get_gem_line_invoice_price_unit(line),
                                "account_id": account.id,
                                "tax_ids": [(6, 0, line.product_id.taxes_id.filtered(
                                    lambda tax: tax.company_id == self.env.company
                                ).ids)],
                            },
                        )
                    )

            if not invoice_line_vals:
                raise UserError(_("There are no service or material lines to invoice in the selected billing batch."))

            invoice = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": batch.partner_id.id,
                    "invoice_date": fields.Date.context_today(batch),
                    "invoice_origin": batch.name,
                    "ref": batch.name,
                    "invoice_line_ids": invoice_line_vals,
                }
            )
            batch.invoice_id = invoice.id

        return self.action_open_invoice()

    def _get_material_line_invoice_price_unit(self, line):
        return line.price_unit

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No invoice is linked to this billing batch yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": self.invoice_id.id,
            "view_mode": "form",
        }

    def action_cancel(self):
        for batch in self:
            if batch.invoice_id and batch.invoice_id.state != "cancel":
                raise UserError(
                    _(
                        "Cancel the linked invoice before cancelling the billing batch."
                    )
                )
            if batch.state == "done":
                batch.order_ids.filtered(lambda order: order.billing_batch_id == batch).write(
                    {
                        "billing_batch_id": False,
                        "billing_date": False,
                    }
                )
                batch.invoice_id = False
            batch.state = "cancel"

    def action_reset_to_draft(self):
        for batch in self:
            if batch.state == "done":
                raise UserError(_("Cancel the confirmed billing batch before resetting it to draft."))
            batch.state = "draft"
            batch._sync_candidate_lines()


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    billing_batch_id = fields.Many2one(
        "jewelry.repair.billing.batch",
        string="Billing Batch",
        readonly=True,
        copy=False,
    )
    billing_date = fields.Date(readonly=True, copy=False)
    amendment_billing_batch_id = fields.Many2one(
        "jewelry.repair.billing.batch",
        string="Billing Batch To Rebuild",
        readonly=True,
        copy=False,
        help="Billing batch rolled back to unlock this order, waiting to be rebuilt.",
    )

    payment_status = fields.Selection(
        [
            ("unbilled", "Unbilled"),
            ("unpaid", "Unpaid"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
        ],
        string="Payment",
        compute="_compute_payment_status",
        search="_search_payment_status",
        store=False,
    )

    def _jewelry_service_summary(self):
        """Aggregate service lines of the recordset by product and unit price.

        Names are taken in the source language so that printed documents stay English.
        """
        summary = {}
        for order in self.sorted(lambda o: (o.delivery_date or fields.Date.today(), o.id)):
            for line in order.service_line_ids:
                key = (line.product_id.id, line.price_unit)
                if key not in summary:
                    summary[key] = {
                        "name": line.product_id.with_context(lang=False).name or line.product_id.name,
                        "quantity": 0.0,
                        "subtotal": 0.0,
                    }
                summary[key]["quantity"] += line.total_quantity
                summary[key]["subtotal"] += line.subtotal
        return sorted(summary.values(), key=lambda item: item["name"])

    def _jewelry_material_summary(self):
        """Aggregate invoiceable material lines of the recordset by product, alloy and price."""
        summary = {}
        for order in self.sorted(lambda o: (o.delivery_date or fields.Date.today(), o.id)):
            for line in order.material_line_ids.filtered("include_in_invoice"):
                key = (
                    line.product_id.id,
                    line.alloy_id.id if line.alloy_id else 0,
                    line.price_unit,
                )
                if key not in summary:
                    summary[key] = {
                        "name": line.product_id.with_context(lang=False).name or line.product_id.name,
                        "alloy_name": line.alloy_id.display_name if line.alloy_id else "",
                        "quantity": 0.0,
                        "weight": 0.0,
                        "subtotal": 0.0,
                    }
                summary[key]["quantity"] += line.quantity
                summary[key]["weight"] += line.weight or 0.0
                summary[key]["subtotal"] += line.subtotal
        return sorted(summary.values(), key=lambda item: (item["name"], item["alloy_name"]))

    def _search_payment_status(self, operator, value):
        values = [value] if operator in ('=', '!=') else list(value)
        negate = operator in ('!=', 'not in')

        domain_by_status = {
            'unbilled': [('billing_batch_id', '=', False)],
            'unpaid': [
                ('billing_batch_id', '!=', False),
                '|',
                ('billing_batch_id.invoice_id', '=', False),
                ('billing_batch_id.invoice_id.payment_state', 'not in', ['paid', 'partial', 'in_payment']),
            ],
            'partial': [('billing_batch_id.invoice_id.payment_state', 'in', ['partial', 'in_payment'])],
            'paid': [('billing_batch_id.invoice_id.payment_state', '=', 'paid')],
        }

        parts = [domain_by_status[v] for v in values if v in domain_by_status]
        if not parts:
            return [('id', '=', False)]

        combined = parts[0]
        for part in parts[1:]:
            combined = ['|'] + combined + part

        if negate:
            ids = self.search(combined).ids
            return [('id', 'not in', ids)]
        return combined

    @api.depends(
        "billing_batch_id",
        "billing_batch_id.invoice_id",
        "billing_batch_id.invoice_id.payment_state",
    )
    def _compute_payment_status(self):
        invoice_ids = self.mapped('billing_batch_id.invoice_id').ids
        payment_states = {}
        if invoice_ids:
            self.env.cr.execute(
                "SELECT id, payment_state FROM account_move WHERE id = ANY(%s)",
                (invoice_ids,)
            )
            payment_states = dict(self.env.cr.fetchall())

        for order in self:
            if not order.billing_batch_id:
                order.payment_status = "unbilled"
            elif not order.billing_batch_id.invoice_id:
                order.payment_status = "unpaid"
            else:
                ps = payment_states.get(order.billing_batch_id.invoice_id.id)
                if ps == "paid":
                    order.payment_status = "paid"
                elif ps in ("partial", "in_payment"):
                    order.payment_status = "partial"
                else:
                    order.payment_status = "unpaid"

    billing_invoice_id = fields.Many2one(
        related="billing_batch_id.invoice_id",
        string="Invoice",
        readonly=True,
    )
    payment_count = fields.Integer(compute="_compute_payment_count")

    @api.depends("billing_batch_id.invoice_id")
    def _compute_payment_count(self):
        for order in self:
            order.payment_count = order.billing_batch_id.payment_count

    def action_open_billing_batch(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Billing Batch"),
            "res_model": "jewelry.repair.billing.batch",
            "res_id": self.billing_batch_id.id,
            "view_mode": "form",
        }

    def action_open_billing_invoice(self):
        self.ensure_one()
        return self.billing_batch_id.action_open_invoice()

    def action_open_payments(self):
        self.ensure_one()
        return self.billing_batch_id.action_open_payments()

    def _get_workflow_fields(self):
        return super()._get_workflow_fields() | {
            "billing_batch_id",
            "billing_date",
            "amendment_billing_batch_id",
        }

    def _amendment_documents(self):
        documents = super()._amendment_documents()
        batch = self.billing_batch_id
        if batch:
            if batch.invoice_id:
                # sudo: a repair manager has no rights on account.move, but needs to see
                # the invoice name and to get a log note on it.
                documents.append(batch.invoice_id.sudo())
            documents.append(batch)
        return documents

    def _close_amendment(self):
        result = super()._close_amendment()
        self.write({"amendment_billing_batch_id": False})
        return result

    def _amendment_payment_warning(self):
        invoice = self.billing_batch_id.invoice_id.sudo()
        if invoice and invoice.payment_state in ("paid", "partial", "in_payment"):
            return _(
                "Invoice %s is paid. Cancelling it removes the reconciliation, and the payment "
                "stays unallocated until you match it against the new invoice."
            ) % invoice.name
        return super()._amendment_payment_warning()

    def _amendment_rollback(self):
        batch = self.billing_batch_id
        if batch:
            # sudo: a repair manager has no accounting rights, and the action is already
            # restricted to managers by action_open_amendment.
            invoice = batch.invoice_id.sudo()
            if invoice:
                if invoice.posted_before:
                    # Posted once: the audit trail forbids deleting it, so cancel instead.
                    # button_cancel resets a posted move to draft on its own.
                    invoice.button_cancel()
                else:
                    # Clear the link first, otherwise action_cancel below reads a deleted record.
                    batch.invoice_id = False
                    invoice.unlink()
            # sudo again: action_cancel reads the invoice state before cancelling the batch.
            batch.sudo().action_cancel()
            batch.sudo().action_reset_to_draft()
            self.amendment_billing_batch_id = batch
        return super()._amendment_rollback()




class JewelryRepairDelivery(models.Model):
    _inherit = "jewelry.repair.delivery"

    billing_status = fields.Selection(
        [
            ("not_billed", "Not Billed"),
            ("billed", "Billed"),
        ],
        compute="_compute_billing_status",
        store=True,
        string="Billing",
    )

    @api.depends("order_ids.billing_batch_id", "state")
    def _compute_billing_status(self):
        for delivery in self:
            if (
                delivery.state == "done"
                and delivery.order_ids
                and all(o.billing_batch_id for o in delivery.order_ids)
            ):
                delivery.billing_status = "billed"
            else:
                delivery.billing_status = "not_billed"

    def action_cancel(self):
        for delivery in self:
            billed_orders = delivery.order_ids.filtered("billing_batch_id")
            if billed_orders:
                raise UserError(
                    _(
                        "You cannot cancel a delivery that already contains billed orders. Cancel the billing batch first."
                    )
                )
        return super().action_cancel()


class AccountMove(models.Model):
    _inherit = "account.move"

    jewelry_billing_batch_ids = fields.One2many(
        "jewelry.repair.billing.batch",
        "invoice_id",
        string="Repair Billing",
    )
    jewelry_billing_batch_count = fields.Integer(compute="_compute_jewelry_billing_batch_count")

    @api.depends("jewelry_billing_batch_ids")
    def _compute_jewelry_billing_batch_count(self):
        for move in self:
            move.jewelry_billing_batch_count = len(move.jewelry_billing_batch_ids)

    def action_open_jewelry_billing(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repair Billing"),
            "res_model": "jewelry.repair.billing.batch",
            "domain": [("id", "in", self.jewelry_billing_batch_ids.ids)],
            "view_mode": "tree,form",
        }
