# -*- coding: utf-8 -*-

from odoo import models

# Reports that must always print in English, regardless of the viewing
# user's UI language (external-facing commercial documents).
FORCE_ENGLISH_REPORTS = {
    "jewelry_repair_base.report_jewelry_repair_order_invoice_document",
    "jewelry_repair_billing.report_jewelry_customer_statement",
}


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name in FORCE_ENGLISH_REPORTS:
            self = self.with_context(lang="en_US")
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    def _render_qweb_html(self, report_ref, docids, data=None):
        report = self._get_report(report_ref)
        if report.report_name in FORCE_ENGLISH_REPORTS:
            self = self.with_context(lang="en_US")
        return super()._render_qweb_html(report_ref, docids, data=data)
