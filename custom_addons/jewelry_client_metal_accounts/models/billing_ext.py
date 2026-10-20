from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class JewelryRepairBillingBatch(models.Model):
    _inherit = "jewelry.repair.billing.batch"

    client_metal_account_id = fields.Many2one(
        "jewelry.client.metal.account",
        string="Client Metal Account",
        domain="[('partner_id', '=', partner_id), ('active', '=', True)]",
        help="Metal account to debit when billing orders with client metal payment.",
    )
    client_metal_account_balance = fields.Float(
        string="Account Balance (fine g)",
        related="client_metal_account_id.balance_fine",
        digits=(16, 4),
        readonly=True,
    )
    total_metal_fine_selected = fields.Float(
        string="Total Metal (fine g)",
        compute="_compute_metal_totals_selected",
        digits=(16, 4),
    )
    total_debit_fine_selected = fields.Float(
        string="Total Debit (fine g)",
        compute="_compute_metal_totals_selected",
        digits=(16, 4),
    )

    @api.depends("line_ids.selected", "line_ids.total_pricing_fine", "line_ids.client_metal_debit_fine")
    def _compute_metal_totals_selected(self):
        for batch in self:
            lines = batch.line_ids.filtered("selected") if batch.state == "draft" else batch.line_ids
            batch.total_metal_fine_selected = sum(lines.mapped("total_pricing_fine"))
            batch.total_debit_fine_selected = sum(lines.mapped("client_metal_debit_fine"))

    @api.depends(
        "order_ids.service_line_ids.subtotal",
        "order_ids.material_line_ids.subtotal",
        "order_ids.material_line_ids.include_in_invoice",
        "order_ids.gem_line_ids.subtotal",
        "order_ids.gem_line_ids.include_in_invoice",
        "line_ids.selected",
        "line_ids.effective_amount_total",
        "line_ids.client_metal_debit_fine",
    )
    def _compute_amount_total(self):
        for batch in self:
            order_to_bl = {bl.order_id.id: bl for bl in batch.line_ids}

            if batch.state == "draft":
                orders = batch.line_ids.filtered("selected").mapped("order_id")
            else:
                orders = batch.order_ids

            total = 0.0
            for order in orders:
                bl = order_to_bl.get(order.id)
                if bl and bl.client_metal_debit_fine:
                    total += bl.effective_amount_total
                else:
                    total += sum(order.service_line_ids.mapped("subtotal"))
                    total += sum(
                        order.material_line_ids.filtered("include_in_invoice").mapped("subtotal")
                    )
                    total += sum(
                        order.gem_line_ids.filtered("include_in_invoice").mapped("subtotal")
                    )
            batch.amount_total = total

    @api.onchange("partner_id")
    def _onchange_partner_id_metal_account(self):
        for batch in self:
            if not batch.partner_id:
                batch.client_metal_account_id = False
                continue
            accounts = self.env["jewelry.client.metal.account"].search([
                ("partner_id", "=", batch.partner_id.id),
                ("active", "=", True),
            ])
            batch.client_metal_account_id = accounts[:1] if len(accounts) == 1 else False

    def _cancel_client_metal_transactions(self):
        for batch in self:
            if not batch.client_metal_account_id or not batch.order_ids:
                continue
            transactions = self.env["jewelry.client.metal.transaction"].search([
                ("account_id", "=", batch.client_metal_account_id.id),
                ("transaction_type", "=", "debit_repair"),
                ("source_model", "=", "jewelry.repair.order"),
                ("source_res_id", "in", batch.order_ids.ids),
                ("state", "=", "posted"),
            ])
            transactions.unlink()

    def _sync_candidate_lines(self):
        """Keep the manually entered metal debit across the rebuild of the lines.

        The base implementation recreates line_ids from scratch, and
        client_metal_debit_fine is typed in by hand, so it would be silently lost
        whenever a batch goes back to draft.
        """
        saved = {
            batch: {
                line.order_id.id: line.client_metal_debit_fine
                for line in batch.line_ids
                if line.client_metal_debit_fine
            }
            for batch in self
        }
        result = super()._sync_candidate_lines()
        for batch, debits in saved.items():
            for line in batch.line_ids:
                debit = debits.get(line.order_id.id)
                if debit:
                    line.client_metal_debit_fine = debit
        return result

    def action_cancel(self):
        self._cancel_client_metal_transactions()
        return super().action_cancel()

    def action_reset_to_draft(self):
        self._cancel_client_metal_transactions()
        return super().action_reset_to_draft()

    def action_confirm(self):
        for batch in self:
            has_debit = any(
                bl.client_metal_debit_fine > 0
                for bl in batch.line_ids
            )
            if has_debit and not batch.client_metal_account_id:
                raise UserError(_(
                    "Select a client metal account before confirming: "
                    "one or more billing lines have a metal debit."
                ))
            # After an order is corrected the debit stays as it was, but the order total
            # it was based on may have shrunk.
            over_debited = batch.line_ids.filtered(
                lambda bl: float_compare(
                    bl.client_metal_debit_fine,
                    bl.total_debit_fine_max,
                    precision_digits=4,
                ) > 0
            )
            if over_debited:
                details = "\n".join(
                    "  • %s: %.4f g > %.4f g"
                    % (bl.order_name, bl.client_metal_debit_fine, bl.total_debit_fine_max)
                    for bl in over_debited
                )
                raise UserError(_(
                    "The metal debit exceeds the order total for the following orders. "
                    "Correct the debit before confirming:\n%s"
                ) % details)
        return super().action_confirm()

    def _user_now(self):
        tz_name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        return datetime.now(pytz.timezone(tz_name)).replace(tzinfo=None)

    def _get_material_line_invoice_price_unit(self, line):
        billing_line = self.line_ids.filtered(
            lambda bl: bl.order_id == line.order_id
        )[:1]
        if not billing_line or not billing_line.total_pricing_fine or not billing_line.client_metal_debit_fine:
            return super()._get_material_line_invoice_price_unit(line)
        ratio = max(0.0, 1.0 - billing_line.client_metal_debit_fine / billing_line.total_pricing_fine)
        return line.price_unit * ratio

    def action_fill_all_metal(self):
        """Set debit = metal cost for all selected (draft) or all (done) billing lines."""
        for batch in self:
            lines = batch.line_ids.filtered("selected") if batch.state == "draft" else batch.line_ids
            lines.filtered(lambda l: l.total_pricing_fine > 0).action_fill_metal()

    def action_fill_all_full(self):
        """Set debit = full order amount for all selected (draft) or all (done) billing lines."""
        for batch in self:
            lines = batch.line_ids.filtered("selected") if batch.state == "draft" else batch.line_ids
            lines.filtered(lambda l: l.total_debit_fine_max > 0).action_fill_full()

    def _should_skip_invoice_for_order(self, order):
        billing_line = self.line_ids.filtered(lambda bl: bl.order_id == order)[:1]
        if billing_line and billing_line.client_metal_debit_fine > 0:
            return billing_line.effective_amount_total <= 0
        return super()._should_skip_invoice_for_order(order)

    def _get_service_line_invoice_price_unit(self, line):
        billing_line = self.line_ids.filtered(lambda bl: bl.order_id == line.order_id)[:1]
        if (
            not billing_line
            or not billing_line.total_pricing_fine
            or billing_line.client_metal_debit_fine <= billing_line.total_pricing_fine
        ):
            return super()._get_service_line_invoice_price_unit(line)
        # Debit exceeds metal-only → extra coverage flows into non-metal lines
        extra_fine = billing_line.client_metal_debit_fine - billing_line.total_pricing_fine
        extra_money = extra_fine / billing_line.total_pricing_fine * billing_line.total_metal_invoice_amount
        non_metal_total = (
            sum(line.order_id.service_line_ids.mapped("subtotal"))
            + sum(line.order_id.gem_line_ids.filtered("include_in_invoice").mapped("subtotal"))
        )
        if not non_metal_total:
            return super()._get_service_line_invoice_price_unit(line)
        ratio = max(0.0, 1.0 - extra_money / non_metal_total)
        return line.price_unit * ratio

    def _get_gem_line_invoice_price_unit(self, line):
        billing_line = self.line_ids.filtered(lambda bl: bl.order_id == line.order_id)[:1]
        if (
            not billing_line
            or not billing_line.total_pricing_fine
            or billing_line.client_metal_debit_fine <= billing_line.total_pricing_fine
        ):
            return super()._get_gem_line_invoice_price_unit(line)
        extra_fine = billing_line.client_metal_debit_fine - billing_line.total_pricing_fine
        extra_money = extra_fine / billing_line.total_pricing_fine * billing_line.total_metal_invoice_amount
        non_metal_total = (
            sum(line.order_id.service_line_ids.mapped("subtotal"))
            + sum(line.order_id.gem_line_ids.filtered("include_in_invoice").mapped("subtotal"))
        )
        if not non_metal_total:
            return super()._get_gem_line_invoice_price_unit(line)
        ratio = max(0.0, 1.0 - extra_money / non_metal_total)
        return line.price_unit * ratio

    def _post_billing_client_metal_transactions(self):
        if not self.client_metal_account_id:
            return
        Transaction = self.env["jewelry.client.metal.transaction"]
        now = self._user_now()
        selected_order_ids = set(self.order_ids.ids)
        for billing_line in self.line_ids.filtered(
            lambda l: l.order_id.id in selected_order_ids and l.client_metal_debit_fine > 0
        ):
            Transaction.create({
                "account_id": self.client_metal_account_id.id,
                "transaction_type": "debit_repair",
                "transaction_date": now,
                "weight_fine": -billing_line.client_metal_debit_fine,
                "state": "posted",
                "source_model": "jewelry.repair.order",
                "source_res_id": billing_line.order_id.id,
                "source_ref": billing_line.order_name,
                "notes": _("Billing batch: %s") % self.name,
            })


class JewelryRepairARSummary(models.Model):
    _inherit = "jewelry.repair.ar.summary"

    def init(self):
        # effective_amount_total is a stored computed field added by this module.
        # On fresh install it doesn't exist yet when init() is called (before _auto_init()).
        # Fallback: join jewelry_repair_order directly via billing_batch_id — always safe.
        # On next server start the column exists and the accurate expression is used.
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'jewelry_repair_billing_line'
              AND column_name = 'effective_amount_total'
        """)
        if self.env.cr.fetchone():
            pending_no_inv = """
                SELECT b.partner_id, SUM(bl.effective_amount_total) AS amount
                FROM jewelry_repair_billing_batch b
                JOIN jewelry_repair_billing_line bl ON bl.batch_id = b.id
                WHERE b.state = 'done'
                  AND (b.invoice_id IS NULL
                       OR (SELECT state FROM account_move WHERE id = b.invoice_id) != 'posted')
                GROUP BY b.partner_id
            """
        else:
            # Fallback: sum order amounts directly — effective_amount_total not yet in DB
            pending_no_inv = """
                SELECT jro.partner_id, SUM(jro.amount_total) AS amount
                FROM jewelry_repair_order jro
                JOIN jewelry_repair_billing_batch b ON b.id = jro.billing_batch_id
                WHERE b.state = 'done'
                  AND (b.invoice_id IS NULL
                       OR (SELECT state FROM account_move WHERE id = b.invoice_id) != 'posted')
                GROUP BY jro.partner_id
            """
        self.env.cr.execute("DROP VIEW IF EXISTS jewelry_repair_ar_summary")
        self.env.cr.execute("""
            CREATE VIEW jewelry_repair_ar_summary AS (
                SELECT
                    p.id AS id,
                    p.id AS partner_id,
                    comp_cur.id AS currency_id,
                    COALESCE(unbilled.amount, 0) AS unbilled_amount,
                    COALESCE(no_inv.amount, 0) AS pending_invoice_amount,
                    COALESCE(inv.residual, 0) AS invoiced_unpaid_amount,
                    COALESCE(adv.credit, 0) AS advance_amount,
                    COALESCE(unbilled.amount, 0)
                        + COALESCE(no_inv.amount, 0)
                        + COALESCE(inv.residual, 0) AS total_outstanding
                FROM res_partner p
                CROSS JOIN (
                    SELECT c.id
                    FROM res_company rc
                    JOIN res_currency c ON c.id = rc.currency_id
                    WHERE rc.id = 1
                ) comp_cur
                LEFT JOIN (
                    SELECT partner_id, SUM(amount_total) AS amount
                    FROM jewelry_repair_order
                    WHERE state = 'delivered' AND billing_batch_id IS NULL
                    GROUP BY partner_id
                ) unbilled ON unbilled.partner_id = p.id
                LEFT JOIN (
                    """ + pending_no_inv + """
                ) no_inv ON no_inv.partner_id = p.id
                LEFT JOIN (
                    SELECT partner_id, SUM(amount_residual) AS residual
                    FROM account_move
                    WHERE move_type = 'out_invoice'
                      AND state = 'posted'
                      AND payment_state NOT IN ('paid', 'reversed')
                    GROUP BY partner_id
                ) inv ON inv.partner_id = p.id
                LEFT JOIN (
                    SELECT aml.partner_id, SUM(-aml.amount_residual) AS credit
                    FROM account_move_line aml
                    JOIN account_account aa ON aa.id = aml.account_id
                    WHERE aa.account_type = 'asset_receivable'
                      AND aml.amount_residual < 0
                      AND aml.parent_state = 'posted'
                    GROUP BY aml.partner_id
                ) adv ON adv.partner_id = p.id
                WHERE
                    COALESCE(unbilled.amount, 0) > 0
                    OR COALESCE(no_inv.amount, 0) > 0
                    OR COALESCE(inv.residual, 0) > 0
                    OR COALESCE(adv.credit, 0) > 0
            )
        """)


class JewelryRepairBillingLine(models.Model):
    _inherit = "jewelry.repair.billing.line"

    total_pricing_fine = fields.Float(
        string="Metal (fine g)",
        compute="_compute_metal_fields",
        digits=(16, 4),
        store=True,
        help="Total fine grams of metal in this order (weight + losses × purity).",
    )
    total_metal_invoice_amount = fields.Monetary(
        string="Metal Invoice Amount",
        compute="_compute_metal_fields",
        store=True,
        currency_field="currency_id",
        help="Sum of subtotals of metal material lines included in invoice.",
    )
    total_debit_fine_max = fields.Float(
        string="Max Debit (fine g)",
        compute="_compute_total_debit_fine_max",
        digits=(16, 4),
        store=True,
        help="Fine grams equivalent to the full order amount at the metal rate.",
    )
    client_metal_debit_fine = fields.Float(
        string="Debit from Account (fine g)",
        digits=(16, 4),
        default=0.0,
        help="Fine grams to debit from the client metal account for this order.",
    )
    metal_amount_reduction = fields.Monetary(
        string="Metal Reduction",
        compute="_compute_effective_amount",
        store=True,
        currency_field="currency_id",
    )
    effective_amount_total = fields.Monetary(
        string="Effective Total",
        compute="_compute_effective_amount",
        store=True,
        currency_field="currency_id",
        help="Order total after subtracting the metal debit equivalent.",
    )

    @api.depends(
        "order_id.material_line_ids.weight",
        "order_id.material_line_ids.weight_loss",
        "order_id.material_line_ids.alloy_id",
        "order_id.material_line_ids.subtotal",
        "order_id.material_line_ids.include_in_invoice",
    )
    def _compute_metal_fields(self):
        for line in self:
            total_fine = 0.0
            total_amount = 0.0
            for mat in line.order_id.material_line_ids.filtered("include_in_invoice"):
                if not mat.alloy_id or not mat.alloy_id.purity:
                    continue
                pricing = (mat.weight or 0.0) + (mat.weight_loss or 0.0)
                total_fine += pricing * mat.alloy_id.purity
                total_amount += mat.subtotal or 0.0
            line.total_pricing_fine = total_fine
            line.total_metal_invoice_amount = total_amount

    @api.depends("order_amount_total", "total_pricing_fine", "total_metal_invoice_amount")
    def _compute_total_debit_fine_max(self):
        for line in self:
            if line.total_metal_invoice_amount and line.total_pricing_fine:
                line.total_debit_fine_max = (
                    (line.order_amount_total or 0.0)
                    * line.total_pricing_fine
                    / line.total_metal_invoice_amount
                )
            else:
                line.total_debit_fine_max = line.total_pricing_fine

    @api.depends(
        "order_amount_total",
        "total_pricing_fine",
        "total_metal_invoice_amount",
        "client_metal_debit_fine",
    )
    def _compute_effective_amount(self):
        for line in self:
            if line.total_pricing_fine and line.client_metal_debit_fine:
                rate = line.total_metal_invoice_amount / line.total_pricing_fine
                reduction = min(
                    line.client_metal_debit_fine * rate,
                    line.order_amount_total or 0.0,
                )
            else:
                reduction = 0.0
            line.metal_amount_reduction = reduction
            line.effective_amount_total = (line.order_amount_total or 0.0) - reduction

    @api.onchange("client_metal_debit_fine")
    def _onchange_clamp_debit_fine(self):
        for line in self:
            if line.client_metal_debit_fine < 0:
                line.client_metal_debit_fine = 0.0
            elif line.total_debit_fine_max and line.client_metal_debit_fine > line.total_debit_fine_max:
                line.client_metal_debit_fine = line.total_debit_fine_max

    @api.constrains("client_metal_debit_fine")
    def _check_debit_not_negative(self):
        for line in self:
            if line.client_metal_debit_fine < 0:
                raise ValidationError(_("Metal debit cannot be negative."))
            if line.total_debit_fine_max and line.client_metal_debit_fine > line.total_debit_fine_max + 1e-6:
                raise ValidationError(_(
                    "Metal debit (%.4f fine g) exceeds the maximum allowed (%.4f fine g)."
                ) % (line.client_metal_debit_fine, line.total_debit_fine_max))

    def action_fill_metal(self):
        """Set debit to cover only the metal material cost."""
        for line in self:
            line.client_metal_debit_fine = line.total_pricing_fine

    def action_fill_full(self):
        """Set debit to cover the full order amount."""
        for line in self:
            line.client_metal_debit_fine = line.total_debit_fine_max
