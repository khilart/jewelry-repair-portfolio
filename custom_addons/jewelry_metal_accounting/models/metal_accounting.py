import logging
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class JewelryRepairExecutor(models.Model):
    _inherit = "jewelry.repair.executor"

    metal_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Metal Storage",
        help="Default metal accounting storage linked to this executor.",
    )


class JewelryRepairOrderOperation(models.Model):
    _inherit = "jewelry.repair.order.operation"

    executor_metal_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Executor Metal Storage",
        related="executor_id.metal_storage_id",
        store=True,
        readonly=True,
    )
    metal_writeoff_document_ids = fields.One2many(
        "jewelry.metal.document",
        "source_operation_id",
        string="Metal Write-Off Documents",
        readonly=True,
    )
    metal_writeoff_document_count = fields.Integer(compute="_compute_metal_writeoff_document_count")

    def _compute_metal_writeoff_document_count(self):
        for operation in self:
            operation.metal_writeoff_document_count = len(operation.metal_writeoff_document_ids)

    def action_view_metal_writeoff_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Metal Write-Off Documents"),
            "res_model": "jewelry.metal.document",
            "view_mode": "tree,form",
            "domain": [("source_operation_id", "=", self.id)],
            "context": {
                "default_source_model": "jewelry.repair.order.operation",
                "default_source_res_id": self.id,
                "default_source_ref": self.display_name,
            },
        }

    metal_loss_ids = fields.One2many(
        "jewelry.metal.loss",
        "source_operation_id",
        string="Metal Loss Entries",
        readonly=True,
    )
    metal_loss_count = fields.Integer(compute="_compute_metal_loss_count")

    def _compute_metal_loss_count(self):
        for operation in self:
            operation.metal_loss_count = len(operation.metal_loss_ids)

    def action_view_metal_losses(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Metal Loss Entries"),
            "res_model": "jewelry.metal.loss",
            "view_mode": "tree,form",
            "domain": [("source_operation_id", "=", self.id)],
        }

    def action_mark_done(self):
        result = super().action_mark_done()
        self._create_metal_loss_entries()
        return result

    def action_return_to_rework(self):
        self.sudo().metal_loss_ids.unlink()
        return super().action_return_to_rework()

    def action_reset_to_pending(self):
        self.sudo().metal_loss_ids.unlink()
        return super().action_reset_to_pending()

    def action_cancel(self):
        self.sudo().metal_loss_ids.unlink()
        return super().action_cancel()

    def _create_metal_loss_entries(self):
        loss_model = self.env["jewelry.metal.loss"]
        for operation in self:
            material_lines = operation.material_line_ids.filtered(
                lambda line: line.consume_from_stock
                and line.alloy_id
                and (line.weight_loss or 0.0) > 0
            )
            if not material_lines:
                continue
            if not operation.executor_metal_storage_id:
                raise UserError(
                    _("Set a metal storage on the operation executor before completing operations with stock-consuming metal materials.")
                )
            for line in material_lines:
                loss_model.sudo().create(
                    {
                        "loss_date": fields.Datetime.now(),
                        "company_id": self.env.company.id,
                        "alloy_id": line.alloy_id.id,
                        "weight_loss": line.weight_loss,
                        "storage_id": operation.executor_metal_storage_id.id,
                        "source_operation_id": operation.id,
                        "source_material_line_id": line.id,
                    }
                )

    def _create_metal_writeoff_documents(self):
        document_model = self.env["jewelry.metal.document"]
        for operation in self:
            material_lines = operation.material_line_ids.filtered(
                lambda line: line.consume_from_stock
                and line.alloy_id
                and line.weight > 0
                and (not line.metal_writeoff_document_id or line.metal_writeoff_document_id.state == "cancel")
            )
            if not material_lines:
                continue
            if not operation.executor_metal_storage_id:
                raise UserError(
                    _("Set a metal storage on the operation executor before completing operations with stock-consuming metal materials.")
                )

            document = document_model.create(
                {
                    "operation_type": "writeoff",
                    "document_date": fields.Datetime.now(),
                    "partner_id": operation.order_id.partner_id.id,
                    "source_storage_id": operation.executor_metal_storage_id.id,
                    "source_model": "jewelry.repair.order.operation",
                    "source_res_id": operation.id,
                    "source_ref": operation.display_name,
                    "source_operation_id": operation.id,
                    "notes": _("Auto-created from completed operation %s") % operation.display_name,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "alloy_id": line.alloy_id.id,
                                "weight": line.weight,
                                "rate_datetime": line._get_effective_rate_datetime(),
                                "notes": line.description or line.product_id.display_name,
                                "source_material_line_id": line.id,
                            },
                        )
                        for line in material_lines
                    ],
                }
            )
            document.action_post()
            material_lines.write({"metal_writeoff_document_id": document.id})


class JewelryMetalStorage(models.Model):
    _name = "jewelry.metal.storage"
    _description = "Jewelry Metal Storage"
    _order = "name, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company.id,
    )
    responsible_user_id = fields.Many2one("res.users", string="Responsible User")
    notes = fields.Text()

    _sql_constraints = [
        ("jewelry_metal_storage_code_company_unique", "unique(code, company_id)", "Storage code must be unique per company."),
    ]


class JewelryMetalDocument(models.Model):
    _name = "jewelry.metal.document"
    _description = "Jewelry Metal Document"
    _order = "document_date desc, id desc"
    _rec_name = "name"

    operation_type = fields.Selection(
        [
            ("receipt", "Receipt"),
            ("transfer", "Transfer"),
            ("writeoff", "Write-Off"),
            ("remelt", "Remelt"),
            ("mixed", "Mixed"),
        ],
        string="Operation Type",
        default="receipt",
    )
    repair_order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        ondelete="cascade",
        index=True,
        copy=False,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancel", "Cancelled"),
        ],
        required=True,
        default="draft",
        copy=False,
    )
    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _("New"))
    document_date = fields.Datetime(required=True, default=fields.Datetime.now)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company.id,
    )
    partner_id = fields.Many2one("res.partner", string="Partner")
    source_storage_id = fields.Many2one("jewelry.metal.storage", string="Source Storage")
    dest_storage_id = fields.Many2one("jewelry.metal.storage", string="Destination Storage")
    source_model = fields.Char(string="Source Model", copy=False)
    source_res_id = fields.Integer(string="Source Record ID", copy=False)
    source_ref = fields.Char(string="Source Reference", copy=False)
    source_operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        string="Source Operation",
        copy=False,
        readonly=True,
    )
    source_repair_order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Source Repair Order",
        compute="_compute_source_repair_order_id",
        store=True,
        readonly=True,
    )

    @api.depends("repair_order_id", "source_operation_id.order_id")
    def _compute_source_repair_order_id(self):
        for doc in self:
            doc.source_repair_order_id = doc.repair_order_id or doc.source_operation_id.order_id
    notes = fields.Text()
    line_ids = fields.One2many("jewelry.metal.document.line", "document_id", string="Lines")
    move_ids = fields.One2many("jewelry.metal.move", "document_id", string="Moves", readonly=True)
    log_ids = fields.One2many("jewelry.metal.document.log", "document_id", string="Logs", readonly=True)
    amount_total = fields.Monetary(
        string="Informational Amount",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
    )
    line_count = fields.Integer(compute="_compute_line_count")
    has_negative_balance_impact = fields.Boolean(compute="_compute_has_negative_balance_impact")

    @api.depends("company_id")
    def _compute_currency_id(self):
        for document in self:
            document.currency_id = document.company_id.currency_id

    @api.depends("line_ids.amount")
    def _compute_amount_total(self):
        for document in self:
            document.amount_total = sum(document.line_ids.mapped("amount"))

    def _compute_line_count(self):
        for document in self:
            document.line_count = len(document.line_ids)

    def _compute_has_negative_balance_impact(self):
        for document in self:
            warning = False
            for line in document.line_ids:
                for storage_id, balance_after in line._get_balance_projection().items():
                    if balance_after < 0:
                        warning = True
                        break
                if warning:
                    break
            document.has_negative_balance_impact = warning

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = sequence.next_by_code("jewelry.metal.document") or _("New")
        documents = super().create(vals_list)
        documents._log_event("create", _("Document created."))
        return documents

    @api.onchange("operation_type")
    def _onchange_operation_type(self):
        if self.operation_type and self.operation_type != "mixed":
            for line in self.line_ids:
                line.operation_type = self.operation_type

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("skip_document_log"):
            return result
        tracked = {
            "operation_type",
            "document_date",
            "partner_id",
            "source_storage_id",
            "dest_storage_id",
            "source_model",
            "source_res_id",
            "source_ref",
            "notes",
        }
        changed = tracked & set(vals)
        if changed:
            self._log_event("write", _("Document updated: %s") % ", ".join(sorted(changed)))
        return result

    def action_post(self):
        move_model = self.env["jewelry.metal.move"]
        for document in self:
            if document.state != "draft":
                raise UserError(_("Only draft metal documents can be posted."))
            if not document.line_ids:
                raise UserError(_("Add at least one line before posting the metal document."))
            document._validate_before_post()
            document.move_ids.filtered(lambda rec: rec.state == "cancel").unlink()
            created_moves = []
            for line in document.line_ids:
                created_moves.extend(line._prepare_move_vals())
            if created_moves:
                move_model.create(created_moves)
            document.with_context(skip_document_log=True).state = "posted"
            document._log_event("post", _("Document posted."))

    def action_cancel(self):
        for document in self:
            if document.state == "cancel":
                continue
            if document.state != "posted":
                document.with_context(skip_document_log=True).state = "cancel"
                document._log_event("cancel", _("Draft document cancelled."))
                continue
            posted_moves = document.move_ids.filtered(lambda rec: rec.state == "posted")
            posted_moves.write({"state": "cancel"})
            document.with_context(skip_document_log=True).state = "cancel"
            document._log_event("cancel", _("Document cancelled and its moves were excluded from balance calculations."))

    def action_reset_to_draft(self):
        for document in self:
            if document.state != "cancel":
                raise UserError(_("Only cancelled documents can be reset to draft."))
            document.move_ids.filtered(lambda move: move.state == "cancel").unlink()
            document.with_context(skip_document_log=True).state = "draft"
            document._log_event("reset_to_draft", _("Document reset to draft."))

    def action_view_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Metal Moves"),
            "res_model": "jewelry.metal.move",
            "view_mode": "tree,pivot,graph,form",
            "domain": [("document_id", "=", self.id)],
            "context": {"default_document_id": self.id},
        }

    def action_fill_from_source_storage(self):
        move_model = self.env["jewelry.metal.move"]
        for document in self:
            if document.state != "draft":
                raise UserError(_("Only draft documents can be filled from source storage balances."))
            if document.operation_type not in ("transfer", "writeoff", "mixed"):
                raise UserError(_("Fill from source storage is only available for transfer, write-off and mixed documents."))
            if not document.source_storage_id:
                raise UserError(_("Set a source storage before filling lines from balances."))

            moves = move_model.search(
                [
                    ("company_id", "=", document.company_id.id),
                    ("storage_id", "=", document.source_storage_id.id),
                    ("state", "=", "posted"),
                    ("document_date", "<=", document.document_date),
                ],
                order="alloy_id, document_date, id",
            )
            balances = {}
            for move in moves:
                balances[move.alloy_id.id] = balances.get(move.alloy_id.id, 0.0) + move.signed_weight
            # Round to the weight precision so float noise does not produce 0.000 lines.
            balances = {alloy_id: round(weight, 3) for alloy_id, weight in balances.items()}

            storage_id = document.source_storage_id.id
            line_vals = []
            if document.operation_type == "transfer":
                # A transfer can only move metal that is there.
                for alloy_id, weight in sorted(balances.items()):
                    if weight > 0:
                        line_vals.append({
                            "operation_type": "transfer",
                            "alloy_id": alloy_id,
                            "weight": weight,
                            "source_storage_id": storage_id,
                            "dest_storage_id": document.dest_storage_id.id,
                        })
                if not line_vals:
                    raise UserError(_("No positive balances were found in the selected source storage on the document date."))
            else:
                # Zeroing the storage: a positive balance is written off,
                # a negative one is brought back to zero by a receipt.
                for alloy_id, weight in sorted(balances.items()):
                    if weight > 0:
                        line_vals.append({
                            "operation_type": "writeoff",
                            "alloy_id": alloy_id,
                            "weight": weight,
                            "source_storage_id": storage_id,
                        })
                    elif weight < 0:
                        line_vals.append({
                            "operation_type": "receipt",
                            "alloy_id": alloy_id,
                            "weight": -weight,
                            "dest_storage_id": storage_id,
                            "rate_datetime": document.document_date,
                        })
                if not line_vals:
                    raise UserError(_("The selected source storage has no non-zero balances on the document date."))

            line_commands = [(5, 0, 0)] + [
                (0, 0, dict(vals, sequence=sequence * 10))
                for sequence, vals in enumerate(line_vals, start=1)
            ]
            values = {"line_ids": line_commands}
            if any(vals["operation_type"] != document.operation_type for vals in line_vals):
                values["operation_type"] = "mixed"
            document.write(values)
            document._log_event("write", _("Lines filled from source storage balances."))

    def _validate_before_post(self):
        for document in self:
            document.line_ids._validate_line_for_operation()

    def _log_event(self, event_type, message, payload_json=False):
        log_model = self.env["jewelry.metal.document.log"].sudo()
        for document in self:
            log_model.create(
                {
                    "document_id": document.id,
                    "event_type": event_type,
                    "event_datetime": fields.Datetime.now(),
                    "user_id": self.env.user.id,
                    "message": message,
                    "payload_json": payload_json or False,
                }
            )


class JewelryMetalDocumentLine(models.Model):
    _name = "jewelry.metal.document.line"
    _description = "Jewelry Metal Document Line"
    _order = "sequence, id"

    def init(self):
        self.env.cr.execute("""
            UPDATE jewelry_metal_document_line l
            SET operation_type = d.operation_type
            FROM jewelry_metal_document d
            WHERE l.document_id = d.id
            AND (l.operation_type IS NULL OR l.operation_type = '')
            AND d.operation_type IS NOT NULL
        """)

    document_id = fields.Many2one(
        "jewelry.metal.document",
        string="Document",
        required=True,
        ondelete="cascade",
    )
    operation_type = fields.Selection(
        [
            ("receipt", "Receipt"),
            ("transfer", "Transfer"),
            ("writeoff", "Write-Off"),
            ("remelt", "Remelt"),
        ],
        required=True,
        default="receipt",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="document_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="document_id.currency_id", store=True, readonly=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Input Alloy", required=True)
    metal_id = fields.Many2one(related="alloy_id.metal_id", store=True, readonly=True)
    weight = fields.Float(string="Input Weight", digits=(16, 3), required=True, default=0.0)
    rate_datetime = fields.Datetime(string="Rate Datetime", default=fields.Datetime.now)
    rate_price_per_gram = fields.Monetary(
        string="Fine price(g)",
        currency_field="currency_id",
        copy=False,
    )
    amount = fields.Monetary(string="Amount", currency_field="currency_id", copy=False)
    output_alloy_id = fields.Many2one("jewelry.metal.alloy", string="Output Alloy")
    output_metal_id = fields.Many2one(related="output_alloy_id.metal_id", store=True, readonly=True)
    output_weight = fields.Float(string="Output Weight", digits=(16, 3))
    loss_weight = fields.Float(
        string="Loss (fine g)", digits=(16, 3),
        compute="_compute_remelt_loss", store=True,
    )
    conversion_ratio = fields.Float(
        string="Loss %", digits=(16, 2),
        compute="_compute_remelt_loss", store=True,
    )
    loss_amount = fields.Monetary(
        string="Loss Amount", currency_field="currency_id",
        compute="_compute_loss_amount", store=True, copy=False,
    )
    source_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Source Storage (Line)",
        help="Overrides document-level source storage for this line.",
    )
    dest_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Destination Storage (Line)",
        help="Overrides document-level destination storage for this line.",
    )
    product_id = fields.Many2one("product.product", string="Product")
    source_material_line_id = fields.Many2one(
        "jewelry.repair.material.line",
        string="Source Material Line",
        readonly=True,
        copy=False,
    )
    notes = fields.Text()
    source_storage_balance = fields.Float(
        string="Source Balance",
        compute="_compute_projected_balances",
        digits=(16, 3),
    )
    source_storage_balance_after = fields.Float(
        string="Source Balance After",
        compute="_compute_projected_balances",
        digits=(16, 3),
    )
    dest_storage_balance = fields.Float(
        string="Destination Balance",
        compute="_compute_projected_balances",
        digits=(16, 3),
    )
    dest_storage_balance_after = fields.Float(
        string="Destination Balance After",
        compute="_compute_projected_balances",
        digits=(16, 3),
    )

    @api.depends(
        "operation_type",
        "source_storage_id",
        "dest_storage_id",
        "document_id.source_storage_id",
        "document_id.dest_storage_id",
        "document_id.state",
        "alloy_id",
        "weight",
        "output_alloy_id",
        "output_weight",
    )
    def _compute_projected_balances(self):
        for line in self:
            eff_source = line.source_storage_id or line.document_id.source_storage_id
            eff_dest = line.dest_storage_id or line.document_id.dest_storage_id
            source_balance = line._get_storage_balance(eff_source, line.alloy_id)
            dest_alloy = line.output_alloy_id if line.operation_type == "remelt" else line.alloy_id
            dest_balance = line._get_storage_balance(eff_dest, dest_alloy)
            line.source_storage_balance = source_balance
            line.dest_storage_balance = dest_balance
            projection = line._get_balance_projection()
            line.source_storage_balance_after = projection.get(eff_source.id, source_balance)
            line.dest_storage_balance_after = projection.get(eff_dest.id, dest_balance)

    @api.depends("operation_type", "weight", "alloy_id", "alloy_id.purity", "output_weight", "output_alloy_id", "output_alloy_id.purity")
    def _compute_remelt_loss(self):
        for line in self:
            if line.operation_type != "remelt" or not line.alloy_id:
                line.loss_weight = 0.0
                line.conversion_ratio = 0.0
                continue
            fine_in = line.weight * (line.alloy_id.purity or 0.0)
            fine_out = (line.output_weight or 0.0) * (line.output_alloy_id.purity or 0.0)
            loss = max(fine_in - fine_out, 0.0)
            line.loss_weight = loss
            line.conversion_ratio = (loss / fine_in * 100.0) if fine_in else 0.0

    @api.depends("loss_weight", "rate_price_per_gram")
    def _compute_loss_amount(self):
        for line in self:
            line.loss_amount = line.loss_weight * (line.rate_price_per_gram or 0.0)

    @api.onchange("alloy_id", "rate_datetime", "operation_type")
    def _onchange_rate_inputs(self):
        self._apply_receipt_pricing()

    @api.onchange("weight")
    def _onchange_weight(self):
        for line in self:
            if line.operation_type == "receipt":
                line.amount = line.rate_price_per_gram * (line.alloy_id.purity or 0.0) * line.weight

    @api.onchange("rate_price_per_gram")
    def _onchange_rate_price_per_gram(self):
        for line in self:
            if line.operation_type == "receipt":
                line.amount = line.rate_price_per_gram * (line.alloy_id.purity or 0.0) * line.weight

    @api.onchange("amount")
    def _onchange_amount(self):
        for line in self:
            if line.operation_type == "receipt":
                fine_weight = (line.alloy_id.purity or 0.0) * line.weight
                if fine_weight:
                    line.rate_price_per_gram = line.amount / fine_weight

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("operation_type") and vals.get("document_id"):
                doc = self.env["jewelry.metal.document"].browse(vals["document_id"])
                if doc.operation_type:
                    vals["operation_type"] = doc.operation_type
        lines = super().create(vals_list)
        # Pricing is applied by onchange when a document is entered through the
        # form; lines created from code need the same rate lookup, unless the
        # caller passed its own price.
        auto_priced = self.browse()
        for line, vals in zip(lines, vals_list):
            if line.operation_type == "receipt" and not {"amount", "rate_price_per_gram"} & set(vals):
                auto_priced |= line
        auto_priced._apply_receipt_pricing()
        return lines


    def _validate_line_for_operation(self):
        for line in self:
            op_type = line.operation_type
            eff_source = line.source_storage_id or line.document_id.source_storage_id
            eff_dest = line.dest_storage_id or line.document_id.dest_storage_id
            if line.weight <= 0:
                raise ValidationError(_("Line weight must be greater than zero."))
            if op_type == "receipt":
                if not line.document_id.partner_id:
                    raise ValidationError(_("Receipt lines require a partner on the document."))
                if not eff_dest:
                    raise ValidationError(_("Receipt lines require a destination storage."))
                if not line.rate_datetime:
                    raise ValidationError(_("Receipt lines require a rate datetime."))
            elif op_type == "transfer":
                if not eff_source or not eff_dest:
                    raise ValidationError(_("Transfer lines require source and destination storages."))
                if eff_source == eff_dest:
                    raise ValidationError(_("Source and destination storages must be different for transfers."))
            elif op_type == "writeoff":
                if not eff_source:
                    raise ValidationError(_("Write-off lines require a source storage."))
            elif op_type == "remelt":
                if not eff_source:
                    raise ValidationError(_("Remelt lines require a source storage."))
                if not eff_dest:
                    raise ValidationError(_("Remelt lines require a destination storage."))
                if not line.output_alloy_id:
                    raise ValidationError(_("Remelt lines require an output alloy."))
                if line.output_weight <= 0:
                    raise ValidationError(_("Remelt lines require output weight greater than zero."))

    def _apply_receipt_pricing(self):
        for line in self:
            if line.operation_type == "receipt":
                if not line.alloy_id or not line.rate_datetime:
                    line.update({"rate_price_per_gram": 0.0, "amount": 0.0})
                    continue
                rate = self.env["jewelry.metal.rate"]._get_latest_rate(
                    line.alloy_id.metal_id,
                    line.rate_datetime,
                    line.company_id,
                )
                if not rate:
                    line.update({"rate_price_per_gram": 0.0, "amount": 0.0})
                    continue
                amount = rate.price_per_gram * (line.alloy_id.purity or 0.0) * line.weight
                line.update({"rate_price_per_gram": rate.price_per_gram, "amount": amount})
            elif line.operation_type == "remelt":
                if not line.alloy_id or not line.rate_datetime:
                    line.rate_price_per_gram = 0.0
                    continue
                rate = self.env["jewelry.metal.rate"]._get_latest_rate(
                    line.alloy_id.metal_id,
                    line.rate_datetime,
                    line.company_id,
                )
                if not rate:
                    line.rate_price_per_gram = 0.0
                    continue
                line.rate_price_per_gram = rate.price_per_gram
            else:
                line.update({"rate_price_per_gram": 0.0, "amount": 0.0})

    def _prepare_move_vals(self):
        self.ensure_one()
        document = self.document_id
        op_type = self.operation_type
        eff_source = self.source_storage_id or document.source_storage_id
        eff_dest = self.dest_storage_id or document.dest_storage_id
        base = {
            "document_id": document.id,
            "document_line_id": self.id,
            "document_date": document.document_date,
            "operation_type": op_type,
            "company_id": document.company_id.id,
            "source_model": document.source_model,
            "source_res_id": document.source_res_id,
            "source_ref": document.source_ref,
            "state": "posted",
            "notes": self.notes or document.notes,
        }
        if op_type == "receipt":
            return [
                dict(base, alloy_id=self.alloy_id.id, storage_id=eff_dest.id, weight_in=self.weight, weight_out=0.0)
            ]
        if op_type == "transfer":
            return [
                dict(base, alloy_id=self.alloy_id.id, storage_id=eff_source.id, weight_in=0.0, weight_out=self.weight),
                dict(base, alloy_id=self.alloy_id.id, storage_id=eff_dest.id, weight_in=self.weight, weight_out=0.0),
            ]
        if op_type == "writeoff":
            return [
                dict(base, alloy_id=self.alloy_id.id, storage_id=eff_source.id, weight_in=0.0, weight_out=self.weight)
            ]
        if op_type == "remelt":
            return [
                dict(base, alloy_id=self.alloy_id.id, storage_id=eff_source.id, weight_in=0.0, weight_out=self.weight),
                dict(base, alloy_id=self.output_alloy_id.id, storage_id=eff_dest.id, weight_in=self.output_weight, weight_out=0.0),
            ]
        return []

    def _get_storage_balance(self, storage, alloy):
        if not storage or not alloy:
            return 0.0
        return self.env["jewelry.metal.move"]._get_balance(alloy, storage, self.company_id, self.document_id.document_date)

    def _get_balance_projection(self):
        self.ensure_one()
        document = self.document_id
        op_type = self.operation_type
        eff_source = self.source_storage_id or document.source_storage_id
        eff_dest = self.dest_storage_id or document.dest_storage_id
        projection = {}
        if op_type in ("transfer", "writeoff", "remelt") and eff_source and self.alloy_id:
            current = self._get_storage_balance(eff_source, self.alloy_id)
            projection[eff_source.id] = current - (self.weight or 0.0)
        if op_type == "transfer" and eff_dest and self.alloy_id:
            current = self._get_storage_balance(eff_dest, self.alloy_id)
            projection[eff_dest.id] = current + (self.weight or 0.0)
        if op_type == "receipt" and eff_dest and self.alloy_id:
            current = self._get_storage_balance(eff_dest, self.alloy_id)
            projection[eff_dest.id] = current + (self.weight or 0.0)
        if op_type == "remelt" and eff_dest and self.output_alloy_id:
            current = self._get_storage_balance(eff_dest, self.output_alloy_id)
            projection[eff_dest.id] = current + (self.output_weight or 0.0)
        return projection


class JewelryMetalMove(models.Model):
    _name = "jewelry.metal.move"
    _description = "Jewelry Metal Move"
    _order = "document_date, id"

    document_id = fields.Many2one("jewelry.metal.document", string="Document", readonly=True, ondelete="cascade")
    document_line_id = fields.Many2one("jewelry.metal.document.line", string="Document Line", readonly=True, ondelete="cascade")
    document_date = fields.Datetime(required=True, readonly=True, index=True)
    operation_type = fields.Selection(
        [
            ("receipt", "Receipt"),
            ("transfer", "Transfer"),
            ("writeoff", "Write-Off"),
            ("remelt", "Remelt"),
        ],
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True, index=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy", required=True, readonly=True, index=True)
    metal_id = fields.Many2one(related="alloy_id.metal_id", store=True, readonly=True)
    storage_id = fields.Many2one("jewelry.metal.storage", string="Storage", required=True, readonly=True, index=True)
    weight_in = fields.Float(string="Weight In", digits=(16, 3), readonly=True)
    weight_out = fields.Float(string="Weight Out", digits=(16, 3), readonly=True)
    signed_weight = fields.Float(string="Turnover", digits=(16, 3), compute="_compute_signed_weight", store=True)
    purity = fields.Float(
        string="Purity",
        digits=(16, 6),
        readonly=True,
        help="Fine metal coefficient of the alloy, captured when the move was created. "
        "Kept on the move so that later edits of the alloy do not distort posted history.",
    )
    fine_in = fields.Float(string="Fine In", digits=(16, 4), compute="_compute_fine_weights", store=True)
    fine_out = fields.Float(string="Fine Out", digits=(16, 4), compute="_compute_fine_weights", store=True)
    fine_signed = fields.Float(string="Fine Turnover", digits=(16, 4), compute="_compute_fine_weights", store=True)
    state = fields.Selection(
        [("posted", "Posted"), ("cancel", "Cancelled")],
        required=True,
        default="posted",
    )
    source_model = fields.Char(string="Source Model", readonly=True, index=True)
    source_res_id = fields.Integer(string="Source Record ID", readonly=True, index=True)
    source_ref = fields.Char(string="Source Reference", readonly=True, index=True)
    source_operation_id = fields.Many2one("jewelry.repair.order.operation", string="Source Operation", related="document_id.source_operation_id", store=True, readonly=True, index=True)
    source_repair_order_id = fields.Many2one("jewelry.repair.order", string="Source Repair Order", related="document_id.source_repair_order_id", store=True, readonly=True, index=True)
    notes = fields.Text(readonly=True)

    @api.depends("weight_in", "weight_out")
    def _compute_signed_weight(self):
        for move in self:
            move.signed_weight = (move.weight_in or 0.0) - (move.weight_out or 0.0)

    @api.depends("weight_in", "weight_out", "purity")
    def _compute_fine_weights(self):
        for move in self:
            purity = move.purity or 0.0
            move.fine_in = (move.weight_in or 0.0) * purity
            move.fine_out = (move.weight_out or 0.0) * purity
            move.fine_signed = move.fine_in - move.fine_out

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("purity") and vals.get("alloy_id"):
                vals["purity"] = self.env["jewelry.metal.alloy"].browse(vals["alloy_id"]).purity
        return super().create(vals_list)

    @api.model
    def _get_balance(self, alloy, storage, company=False, at_datetime=False):
        if not alloy or not storage:
            return 0.0
        company = company or self.env.company
        domain = [
            ("alloy_id", "=", alloy.id),
            ("storage_id", "=", storage.id),
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
        ]
        if at_datetime:
            domain.append(("document_date", "<=", at_datetime))
        # Aggregate in PostgreSQL: one SUM query instead of loading every move of
        # the alloy/storage combination into memory.
        [(balance,)] = self._read_group(domain, aggregates=["signed_weight:sum"])
        return balance or 0.0


class JewelryMetalDocumentLog(models.Model):
    _name = "jewelry.metal.document.log"
    _description = "Jewelry Metal Document Log"
    _order = "event_datetime desc, id desc"

    document_id = fields.Many2one(
        "jewelry.metal.document",
        string="Document",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    event_type = fields.Selection(
        [
            ("create", "Created"),
            ("write", "Updated"),
            ("post", "Posted"),
            ("cancel", "Cancelled"),
            ("reset_to_draft", "Reset To Draft"),
        ],
        required=True,
        readonly=True,
    )
    event_datetime = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", string="User", required=True, readonly=True, default=lambda self: self.env.user.id)
    message = fields.Char(required=True, readonly=True)
    payload_json = fields.Text(readonly=True)


class JewelryMetalStockStatementWizard(models.TransientModel):
    _name = "jewelry.metal.stock.statement.wizard"
    _description = "Jewelry Metal Stock Statement Wizard"
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name")

    @api.depends("date_from", "date_to")
    def _compute_display_name(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                wizard.display_name = _("Balances and Turnover %s — %s", wizard.date_from, wizard.date_to)
            else:
                wizard.display_name = _("Balances and Turnover")

    period_preset = fields.Selection(
        [
            ("today", "Today"),
            ("this_week", "This Week"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
            ("this_year", "This Year"),
            ("custom", "Custom"),
        ],
        string="Period Preset",
        required=True,
        default="this_month",
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    storage_ids = fields.Many2many("jewelry.metal.storage", string="Storages")
    alloy_ids = fields.Many2many("jewelry.metal.alloy", string="Alloys")
    include_zero_lines = fields.Boolean(string="Include Zero Lines")
    line_ids = fields.One2many(
        "jewelry.metal.stock.statement.line",
        "wizard_id",
        string="Statement Lines",
        readonly=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("The start date must be earlier than or equal to the end date."))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        preset = values.get("period_preset", "this_month")
        date_from, date_to = self._get_preset_dates(preset)
        values["date_from"] = date_from
        values["date_to"] = date_to
        return values

    def _get_preset_dates(self, preset):
        today = fields.Date.context_today(self)
        if preset == "today":
            return today, today
        if preset == "this_week":
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            return week_start, week_end
        if preset == "this_month":
            date_from = today.replace(day=1)
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            date_to = next_month - timedelta(days=1)
            return date_from, date_to
        if preset == "last_month":
            current_month_start = today.replace(day=1)
            last_month_end = current_month_start - timedelta(days=1)
            return last_month_end.replace(day=1), last_month_end
        if preset == "this_year":
            return today.replace(month=1, day=1), today.replace(month=12, day=31)
        return today, today

    @api.onchange("period_preset")
    def _onchange_period_preset(self):
        for wizard in self:
            if not wizard.period_preset or wizard.period_preset == "custom":
                continue
            wizard.date_from, wizard.date_to = wizard._get_preset_dates(wizard.period_preset)

    def _get_datetime_bounds(self):
        self.ensure_one()
        datetime_from = datetime.combine(self.date_from, time.min)
        datetime_to_exclusive = datetime.combine(self.date_to + timedelta(days=1), time.min)
        return fields.Datetime.to_string(datetime_from), fields.Datetime.to_string(datetime_to_exclusive)

    def action_open_lines(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "jewelry_metal_accounting.action_jewelry_metal_stock_statement_line"
        )
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {
            "statement_wizard_id": self.id,
            "search_default_group_storage": 1,
            "search_default_group_alloy": 1,
        }
        return action

    @api.model
    def action_open_statement(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Balances and Turnover"),
            "res_model": "jewelry.metal.stock.statement.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("jewelry_metal_accounting.view_jewelry_metal_stock_statement_wizard_form").id,
            "target": "current",
        }

    def action_build_statement(self):
        self.ensure_one()
        self._check_dates()
        self.line_ids.unlink()

        datetime_from, datetime_to_exclusive = self._get_datetime_bounds()
        where_clauses = [
            "m.state = 'posted'",
            "m.company_id = %s",
            "m.document_date < %s",
        ]
        params = [
            datetime_from,           # opening_balance: document_date < date_from
            datetime_from,           # weight_in: document_date >= date_from
            datetime_to_exclusive,   # weight_in: document_date < date_to_exclusive
            datetime_from,           # weight_out: document_date >= date_from
            datetime_to_exclusive,   # weight_out: document_date < date_to_exclusive
            self.env.company.id,     # WHERE company_id
            datetime_to_exclusive,   # WHERE document_date < date_to_exclusive
        ]

        if self.storage_ids:
            where_clauses.append("m.storage_id IN %s")
            params.append(tuple(self.storage_ids.ids))
        if self.alloy_ids:
            where_clauses.append("m.alloy_id IN %s")
            params.append(tuple(self.alloy_ids.ids))

        query = f"""
            SELECT
                m.company_id,
                m.storage_id,
                m.alloy_id,
                SUM(CASE WHEN m.document_date < %s THEN m.signed_weight ELSE 0 END) AS opening_balance,
                SUM(CASE WHEN m.document_date >= %s AND m.document_date < %s THEN m.weight_in ELSE 0 END) AS weight_in,
                SUM(CASE WHEN m.document_date >= %s AND m.document_date < %s THEN m.weight_out ELSE 0 END) AS weight_out,
                SUM(m.signed_weight) AS closing_balance
            FROM jewelry_metal_move m
            WHERE {" AND ".join(where_clauses)}
            GROUP BY m.company_id, m.storage_id, m.alloy_id
            ORDER BY m.storage_id, m.alloy_id
        """
        # Flush pending ORM writes so the raw SQL below sees moves created
        # earlier in the same transaction (e.g. chained calls or tests).
        self.env.flush_all()
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        alloy_ids = {row["alloy_id"] for row in rows if row.get("alloy_id")}
        purity_by_alloy = {
            a["id"]: a["purity"]
            for a in self.env["jewelry.metal.alloy"].browse(list(alloy_ids)).read(["purity"])
        }

        line_vals = []
        for row in rows:
            if not self.include_zero_lines and not any(
                (row[field_name] or 0.0)
                for field_name in ("opening_balance", "weight_in", "weight_out", "closing_balance")
            ):
                continue
            closing = row["closing_balance"] or 0.0
            purity = purity_by_alloy.get(row["alloy_id"], 0.0)
            values = {
                "wizard_id": self.id,
                "company_id": row["company_id"],
                "storage_id": row["storage_id"],
                "alloy_id": row["alloy_id"],
                "opening_balance": row["opening_balance"] or 0.0,
                "weight_in": row["weight_in"] or 0.0,
                "weight_out": row["weight_out"] or 0.0,
                "closing_balance": closing,
                "closing_balance_fine": closing * purity,
            }
            line_vals.append(values)

        if line_vals:
            self.env["jewelry.metal.stock.statement.line"].create(line_vals)

        return False

    def action_print_statement(self):
        self.ensure_one()
        return self.env.ref(
            "jewelry_metal_accounting.action_report_metal_stock_statement"
        ).report_action(self)


class JewelryMetalStockStatementLine(models.TransientModel):
    _name = "jewelry.metal.stock.statement.line"
    _description = "Jewelry Metal Stock Statement Line"
    _order = "storage_id, alloy_id, id"

    wizard_id = fields.Many2one(
        "jewelry.metal.stock.statement.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    period_preset = fields.Selection(related="wizard_id.period_preset", readonly=True)
    date_from = fields.Date(related="wizard_id.date_from", readonly=True)
    date_to = fields.Date(related="wizard_id.date_to", readonly=True)
    include_zero_lines = fields.Boolean(related="wizard_id.include_zero_lines", readonly=True)
    storage_filter_ids = fields.Many2many(related="wizard_id.storage_ids", readonly=True)
    alloy_filter_ids = fields.Many2many(related="wizard_id.alloy_ids", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    storage_id = fields.Many2one("jewelry.metal.storage", string="Storage", readonly=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy", readonly=True)
    metal_id = fields.Many2one("jewelry.metal", string="Metal", related="alloy_id.metal_id", readonly=True)
    opening_balance = fields.Float(string="Opening Balance", digits=(16, 3), readonly=True)
    weight_in = fields.Float(string="Weight In", digits=(16, 3), readonly=True)
    weight_out = fields.Float(string="Weight Out", digits=(16, 3), readonly=True)
    closing_balance = fields.Float(string="Closing Balance", digits=(16, 3), readonly=True)
    closing_balance_fine = fields.Float(
        string="Closing Balance (fine g)",
        digits=(16, 4),
        readonly=True,
    )
    move_count = fields.Integer(compute="_compute_move_count")

    def _compute_move_count(self):
        for line in self:
            if not line.wizard_id or not line.storage_id or not line.alloy_id:
                line.move_count = 0
                continue
            datetime_from, datetime_to_exclusive = line.wizard_id._get_datetime_bounds()
            line.move_count = self.env["jewelry.metal.move"].search_count([
                ("storage_id", "=", line.storage_id.id),
                ("alloy_id", "=", line.alloy_id.id),
                ("state", "=", "posted"),
                ("document_date", ">=", datetime_from),
                ("document_date", "<", datetime_to_exclusive),
            ])

    def action_view_moves(self):
        self.ensure_one()
        datetime_from, datetime_to_exclusive = self.wizard_id._get_datetime_bounds()
        period = f"{self.wizard_id.date_from} — {self.wizard_id.date_to}"
        return {
            "type": "ir.actions.act_window",
            "name": _("%(alloy)s / %(storage)s (%(period)s)", alloy=self.alloy_id.display_name, storage=self.storage_id.display_name, period=period),
            "res_model": "jewelry.metal.move",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("jewelry_metal_accounting.view_jewelry_metal_move_period_tree").id, "tree"),
                (False, "form"),
            ],
            "domain": [
                ("storage_id", "=", self.storage_id.id),
                ("alloy_id", "=", self.alloy_id.id),
                ("state", "=", "posted"),
                ("document_date", ">=", datetime_from),
                ("document_date", "<", datetime_to_exclusive),
            ],
        }


class JewelryRepairMaterialLine(models.Model):
    _inherit = "jewelry.repair.material.line"

    metal_writeoff_document_id = fields.Many2one(
        "jewelry.metal.document",
        string="Metal Write-Off Document",
        readonly=True,
        copy=False,
    )
    source_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Write-Off Storage",
    )
    return_storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Return Storage",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("source_storage_id") and vals.get("order_operation_id"):
                operation = self.env["jewelry.repair.order.operation"].browse(
                    vals["order_operation_id"]
                )
                if operation.executor_metal_storage_id:
                    vals["source_storage_id"] = operation.executor_metal_storage_id.id
        return super().create(vals_list)

    @api.onchange("order_operation_id")
    def _onchange_order_operation_source_storage(self):
        for line in self:
            operation = line.order_operation_id
            if operation and operation.executor_metal_storage_id and not line.source_storage_id:
                line.source_storage_id = operation.executor_metal_storage_id


class JewelryRepairOrder(models.Model):
    _inherit = "jewelry.repair.order"

    def _get_metal_document(self):
        self.ensure_one()
        return self.env["jewelry.metal.document"].search(
            [("repair_order_id", "=", self.id)], limit=1
        )

    def _check_uncovered_material_lines(self):
        self.ensure_one()
        uncovered = self.material_line_ids.filtered(
            lambda l: l.consume_from_stock
            and not l.include_in_invoice
            and not l.return_to_storage
        )
        if uncovered:
            return _(
                "%d material line(s) are consumed from stock but neither billed to the client nor returned to storage."
            ) % len(uncovered)
        return False

    def _sync_metal_documents(self):
        Document = self.env["jewelry.metal.document"]
        Line = self.env["jewelry.metal.document.line"]
        for order in self:
            # Validate return_to_storage lines have return_storage_id
            invalid = order.material_line_ids.filtered(
                lambda l: l.return_to_storage and not l.return_storage_id
            )
            if invalid:
                raise UserError(_("Fill in Return Storage for all lines marked as 'Return to Storage'."))

            # Collect lines that will produce moves
            writeoff_lines = order.material_line_ids.filtered(
                lambda l: l.consume_from_stock and l.alloy_id and (l.weight or 0.0) > 0
            )
            receipt_lines = order.material_line_ids.filtered(
                lambda l: l.return_to_storage and l.return_storage_id and l.alloy_id and (l.weight or 0.0) > 0
            )

            # Validate write-off storages for writeoff lines
            missing_storage = writeoff_lines.filtered(lambda l: not l.source_storage_id)
            if missing_storage:
                raise UserError(
                    _("Set a write-off storage for the following material lines: %s")
                    % ", ".join(missing_storage.mapped("product_id.display_name"))
                )

            has_writeoff = bool(writeoff_lines)
            has_receipt = bool(receipt_lines)
            if has_writeoff and has_receipt:
                doc_operation_type = "mixed"
            elif has_writeoff:
                doc_operation_type = "writeoff"
            else:
                doc_operation_type = "receipt"

            document = order._get_metal_document()
            if document:
                if document.state == "posted":
                    document.action_cancel()
                    document.action_reset_to_draft()
                elif document.state == "cancel":
                    document.action_reset_to_draft()
                document.write({"operation_type": doc_operation_type})
                document.line_ids.unlink()
            else:
                document = Document.create({
                    "repair_order_id": order.id,
                    "operation_type": doc_operation_type,
                    "partner_id": order.partner_id.id,
                    "document_date": fields.Datetime.now(),
                    "source_model": "jewelry.repair.order",
                    "source_res_id": order.id,
                    "source_ref": order.name,
                    "notes": _("Auto-created from repair order %s") % order.name,
                })

            doc_lines = []
            for mat in writeoff_lines:
                doc_lines.append({
                    "document_id": document.id,
                    "operation_type": "writeoff",
                    "alloy_id": mat.alloy_id.id,
                    "weight": mat.weight,
                    "source_storage_id": mat.source_storage_id.id,
                    "product_id": mat.product_id.id if mat.product_id else False,
                    "source_material_line_id": mat.id,
                    "notes": mat.description or (mat.product_id.display_name if mat.product_id else False),
                })
            for mat in receipt_lines:
                doc_lines.append({
                    "document_id": document.id,
                    "operation_type": "receipt",
                    "alloy_id": mat.alloy_id.id,
                    "weight": mat.weight,
                    "dest_storage_id": mat.return_storage_id.id,
                    "product_id": mat.product_id.id if mat.product_id else False,
                    "source_material_line_id": mat.id,
                    "notes": mat.description or (mat.product_id.display_name if mat.product_id else False),
                })

            if doc_lines:
                Line.create(doc_lines)
                document.action_post()
            else:
                document.unlink()

    def action_sync_metal_documents(self):
        self.ensure_one()
        warning = self._check_uncovered_material_lines()
        self._sync_metal_documents()
        if warning:
            return self._weight_warning_notification(warning)

    # ── hooks defined empty in jewelry_repair_base ───────────────────────────
    def _metal_cleanup_documents(self):
        for order in self:
            doc = order._get_metal_document()
            if doc:
                doc.action_cancel()
                doc.unlink()
        return super()._metal_cleanup_documents()

    def _collect_pre_acceptance_warnings(self):
        self.ensure_one()
        warnings = super()._collect_pre_acceptance_warnings()
        if not self._get_metal_document():
            uncovered = self._check_uncovered_material_lines()
            if uncovered:
                warnings.append(uncovered)
            self._sync_metal_documents()
        return warnings


class JewelryMetalLoss(models.Model):
    _name = "jewelry.metal.loss"
    _description = "Jewelry Metal Loss Entry"
    _order = "loss_date desc, id desc"

    def init(self):
        self.env.cr.execute("""
            UPDATE jewelry_metal_loss
            SET loss_type = 'material'
            WHERE loss_type IS NULL OR loss_type = ''
        """)

    name = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("jewelry.metal.loss"),
    )
    loss_date = fields.Datetime(string="Date", required=True, readonly=True)
    loss_type = fields.Selection(
        [
            ("material", "Material Loss"),
            ("recoverable", "Recoverable Loss"),
            ("irrecoverable", "Irrecoverable Loss"),
            ("setting", "Gem Setting Loss"),
        ],
        string="Loss Type",
        required=True,
        default="material",
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy", required=True, readonly=True)
    metal_id = fields.Many2one(
        "jewelry.metal",
        string="Metal",
        related="alloy_id.metal_id",
        store=True,
        readonly=True,
    )
    weight_loss = fields.Float(string="Loss Weight (g)", digits=(16, 3), required=True, readonly=True)
    storage_id = fields.Many2one(
        "jewelry.metal.storage",
        string="Storage",
        required=True,
        readonly=True,
    )
    source_operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        string="Operation",
        readonly=True,
        ondelete="cascade",
    )
    source_repair_order_id = fields.Many2one(
        "jewelry.repair.order",
        string="Repair Order",
        related="source_operation_id.order_id",
        store=True,
        readonly=True,
    )
    source_material_line_id = fields.Many2one(
        "jewelry.repair.material.line",
        string="Material Line",
        readonly=True,
    )
