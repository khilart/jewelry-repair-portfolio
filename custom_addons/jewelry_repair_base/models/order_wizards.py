from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairAmendmentWizard(models.TransientModel):
    _name = "jewelry.repair.amendment.wizard"
    _description = "Unlock Delivered Order For Editing"

    order_id = fields.Many2one("jewelry.repair.order", string="Repair Order", required=True, readonly=True)
    reason = fields.Char(string="Reason", required=True)
    document_summary = fields.Char(
        string="Documents To Cancel",
        compute="_compute_document_summary",
    )
    payment_warning = fields.Char(
        string="Payment Warning",
        compute="_compute_payment_warning",
    )

    @api.depends("order_id")
    def _compute_payment_warning(self):
        for wizard in self:
            wizard.payment_warning = wizard.order_id._amendment_payment_warning()

    @api.depends("order_id")
    def _compute_document_summary(self):
        for wizard in self:
            if not wizard.order_id:
                wizard.document_summary = False
                continue
            wizard.document_summary = ", ".join(
                document.display_name for document in wizard.order_id._amendment_documents()
            )

    def action_confirm(self):
        self.ensure_one()
        self.order_id._open_amendment(self.reason)
        return {"type": "ir.actions.act_window_close"}


class JewelryRepairForceReadyWizard(models.TransientModel):
    _name = "jewelry.repair.force.ready.wizard"
    _description = "Force Mark Order Ready"

    order_id = fields.Many2one("jewelry.repair.order", required=True)
    pending_count = fields.Integer(string="Uncompleted Operations", readonly=True)

    def action_confirm(self):
        self.ensure_one()
        now = fields.Datetime.now()
        ops = self.order_id.order_operation_ids.filtered(
            lambda o: o.state not in ("done", "cancel")
        )
        for op in ops:
            values = {"state": "done", "done_at": now}
            if not op.started_at:
                values["started_at"] = now
            op.write(values)
        self.order_id.write({"state": "ready"})
        self.order_id._compute_area_losses()

class JewelryRepairWeightDiscrepancyWizard(models.TransientModel):
    _name = "jewelry.repair.weight.discrepancy.wizard"
    _description = "Confirm Weight Discrepancy on Acceptance"

    order_id = fields.Many2one("jewelry.repair.order", required=True, ondelete="cascade")
    message = fields.Text(readonly=True)

    def action_confirm(self):
        self.ensure_one()
        return self.order_id.with_context(
            weight_discrepancy_confirmed=True
        ).action_accept_ready_item()


class ReassignNextOperationWizard(models.TransientModel):
    _name = "jewelry.repair.reassign.next.wizard"
    _description = "Reassign Next Operation"

    operation_id = fields.Many2one(
        "jewelry.repair.order.operation",
        required=True,
        ondelete="cascade",
    )
    reassign_self = fields.Boolean(default=False)
    new_executor_id = fields.Many2one(
        "jewelry.repair.executor",
        string="Assign To",
    )

    def action_reassign(self):
        self.ensure_one()
        target = self.operation_id if self.reassign_self else self.operation_id.next_order_operation_id
        if target:
            vals = {"executor_id": self.new_executor_id.id}
            if self.new_executor_id.user_id:
                vals["assigned_user_id"] = self.new_executor_id.user_id.id
            target.sudo().write(vals)
