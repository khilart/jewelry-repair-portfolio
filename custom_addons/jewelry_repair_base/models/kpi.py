from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class JewelryRepairKpiServiceLine(models.TransientModel):
    _name = "jewelry.repair.kpi.service.line"
    _description = "KPI Dashboard Service Line"
    _order = "amount desc"

    dashboard_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    dashboard_prev_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    service_name = fields.Char(string="Service", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    quantity = fields.Float(string="Qty", digits=(16, 2), readonly=True)
    order_count = fields.Integer(string="Orders", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    outsource_cost = fields.Monetary(string="Outsource Cost", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
    )

    @api.depends("dashboard_id", "dashboard_prev_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (rec.dashboard_id or rec.dashboard_prev_id).currency_id

    def action_view_service_lines(self):
        self.ensure_one()
        dashboard = self.dashboard_id or self.dashboard_prev_id
        is_prev = bool(self.dashboard_prev_id)
        date_from = dashboard.date_prev_from if is_prev else dashboard.date_from
        date_to = dashboard.date_prev_to if is_prev else None
        domain = [
            ("order_id.state", "=", "delivered"),
            ("order_id.delivery_date", ">=", str(date_from)),
            ("product_id", "=", self.product_id.id),
        ]
        if date_to:
            domain.append(("order_id.delivery_date", "<", str(date_to)))
        return {
            "type": "ir.actions.act_window",
            "name": self.service_name,
            "res_model": "jewelry.repair.service.line",
            "view_mode": "list",
            "domain": domain,
        }


class JewelryRepairKpiMaterialLine(models.TransientModel):
    _name = "jewelry.repair.kpi.material.line"
    _description = "KPI Dashboard Material Line"
    _order = "amount desc"

    dashboard_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    dashboard_prev_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    alloy_name = fields.Char(string="Alloy / Material", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", readonly=True)
    quantity = fields.Float(string="Weight (g)", digits=(16, 3), readonly=True)
    order_count = fields.Integer(string="Orders", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
    )

    @api.depends("dashboard_id", "dashboard_prev_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (rec.dashboard_id or rec.dashboard_prev_id).currency_id

    def action_view_material_lines(self):
        self.ensure_one()
        dashboard = self.dashboard_id or self.dashboard_prev_id
        is_prev = bool(self.dashboard_prev_id)
        date_from = dashboard.date_prev_from if is_prev else dashboard.date_from
        date_to = dashboard.date_prev_to if is_prev else None
        domain = [
            ("order_id.state", "=", "delivered"),
            ("order_id.delivery_date", ">=", str(date_from)),
            ("include_in_invoice", "=", True),
        ]
        if self.alloy_id:
            domain.append(("alloy_id", "=", self.alloy_id.id))
        elif self.product_id:
            domain.append(("product_id", "=", self.product_id.id))
        if date_to:
            domain.append(("order_id.delivery_date", "<", str(date_to)))
        return {
            "type": "ir.actions.act_window",
            "name": self.alloy_name,
            "res_model": "jewelry.repair.material.line",
            "view_mode": "list",
            "domain": domain,
        }


class JewelryRepairKpiClientServiceLine(models.TransientModel):
    _name = "jewelry.repair.kpi.client.service.line"
    _description = "KPI Dashboard Client Service Detail"
    _order = "amount desc"

    client_line_id = fields.Many2one("jewelry.repair.kpi.client.line", ondelete="cascade", required=True)
    service_name = fields.Char(string="Service", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    quantity = fields.Float(string="Qty", digits=(16, 2), readonly=True)
    order_count = fields.Integer(string="Orders", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", related="client_line_id.currency_id")


class JewelryRepairKpiClientMaterialLine(models.TransientModel):
    _name = "jewelry.repair.kpi.client.material.line"
    _description = "KPI Dashboard Client Material Detail"
    _order = "amount desc"

    client_line_id = fields.Many2one("jewelry.repair.kpi.client.line", ondelete="cascade", required=True)
    alloy_name = fields.Char(string="Alloy / Material", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    alloy_id = fields.Many2one("jewelry.metal.alloy", readonly=True)
    quantity = fields.Float(string="Weight (g)", digits=(16, 3), readonly=True)
    order_count = fields.Integer(string="Orders", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", related="client_line_id.currency_id")


class JewelryRepairKpiClientLine(models.TransientModel):
    _name = "jewelry.repair.kpi.client.line"
    _description = "KPI Dashboard Client Line"
    _order = "amount desc"

    dashboard_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    dashboard_prev_id = fields.Many2one("jewelry.repair.kpi.dashboard", ondelete="cascade")
    partner_name = fields.Char(string="Client", readonly=True)
    order_count = fields.Integer(string="Orders", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
    )
    service_ids = fields.One2many("jewelry.repair.kpi.client.service.line", "client_line_id", string="Services")
    material_ids = fields.One2many("jewelry.repair.kpi.client.material.line", "client_line_id", string="Materials")

    @api.depends("dashboard_id", "dashboard_prev_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (rec.dashboard_id or rec.dashboard_prev_id).currency_id


class JewelryRepairKpiDashboard(models.TransientModel):
    _name = "jewelry.repair.kpi.dashboard"
    _description = "Jewelry Repair KPI Dashboard"
    _rec_name = "display_name"

    display_name = fields.Char(default=lambda self: _("Financial Dashboard"), readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )
    date_from = fields.Date(readonly=True)
    date_prev_from = fields.Date(readonly=True)
    date_prev_to = fields.Date(readonly=True)

    waiting_amount = fields.Monetary(string="Waiting", currency_field="currency_id", readonly=True)
    waiting_count = fields.Integer(string="Waiting Orders", readonly=True)

    in_progress_amount = fields.Monetary(string="In Progress", currency_field="currency_id", readonly=True)
    in_progress_count = fields.Integer(string="In Progress Orders", readonly=True)

    ready_amount = fields.Monetary(string="Ready for Delivery", currency_field="currency_id", readonly=True)
    ready_count = fields.Integer(string="Ready for Delivery Orders", readonly=True)

    revenue_month_services = fields.Monetary(string="Services This Month", currency_field="currency_id", readonly=True)
    revenue_month_materials = fields.Monetary(string="Materials This Month", currency_field="currency_id", readonly=True)
    revenue_month = fields.Monetary(string="Total This Month", currency_field="currency_id", readonly=True)
    revenue_month_count = fields.Integer(string="Delivered This Month", readonly=True)
    paid_month = fields.Monetary(string="Paid This Month", currency_field="currency_id", readonly=True)

    revenue_prev_month_services = fields.Monetary(string="Services Last Month", currency_field="currency_id", readonly=True)
    revenue_prev_month_materials = fields.Monetary(string="Materials Last Month", currency_field="currency_id", readonly=True)
    revenue_prev_month = fields.Monetary(string="Total Last Month", currency_field="currency_id", readonly=True)
    revenue_prev_month_count = fields.Integer(string="Delivered Last Month", readonly=True)
    paid_prev_month = fields.Monetary(string="Paid Last Month", currency_field="currency_id", readonly=True)

    service_month_ids = fields.One2many(
        "jewelry.repair.kpi.service.line", "dashboard_id",
        string="Service Lines This Month",
    )
    material_month_ids = fields.One2many(
        "jewelry.repair.kpi.material.line", "dashboard_id",
        string="Material Lines This Month",
    )
    service_prev_ids = fields.One2many(
        "jewelry.repair.kpi.service.line", "dashboard_prev_id",
        string="Service Lines Last Month",
    )
    material_prev_ids = fields.One2many(
        "jewelry.repair.kpi.material.line", "dashboard_prev_id",
        string="Material Lines Last Month",
    )
    client_month_ids = fields.One2many(
        "jewelry.repair.kpi.client.line", "dashboard_id",
        string="Clients This Month",
    )
    client_prev_ids = fields.One2many(
        "jewelry.repair.kpi.client.line", "dashboard_prev_id",
        string="Clients Last Month",
    )

    @api.model
    def _get_order_action(self, domain, name):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "jewelry.repair.order",
            "view_mode": "list,form",
            "domain": domain,
        }

    def action_view_delivered_month(self):
        today = fields.Date.today()
        month_start = today.replace(day=1)
        return self._get_order_action(
            [("state", "=", "delivered"), ("delivery_date", ">=", str(month_start))],
            _("Delivered This Month"),
        )

    def action_view_delivered_prev_month(self):
        today = fields.Date.today()
        if today.month == 1:
            prev_start = today.replace(year=today.year - 1, month=12, day=1)
            prev_end = today.replace(day=1)
        else:
            prev_start = today.replace(month=today.month - 1, day=1)
            prev_end = today.replace(day=1)
        return self._get_order_action(
            [("state", "=", "delivered"), ("delivery_date", ">=", str(prev_start)), ("delivery_date", "<", str(prev_end))],
            _("Delivered Last Month"),
        )

    def action_view_in_progress(self):
        return self._get_order_action([("state", "=", "in_progress")], _("In Progress"))

    def action_view_ready(self):
        return self._get_order_action(
            [("state", "in", ["ready", "ready_for_delivery"])], _("Ready for Delivery")
        )

    def action_view_waiting(self):
        return self._get_order_action([("state", "=", "draft")], _("Waiting"))

    def _get_service_line_action(self, date_from, date_to, name):
        domain = [
            ("order_id.state", "=", "delivered"),
            ("order_id.delivery_date", ">=", str(date_from)),
        ]
        if date_to:
            domain.append(("order_id.delivery_date", "<", str(date_to)))
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "jewelry.repair.service.line",
            "view_mode": "list",
            "domain": domain,
        }

    def _get_material_line_action(self, date_from, date_to, name):
        domain = [
            ("order_id.state", "=", "delivered"),
            ("order_id.delivery_date", ">=", str(date_from)),
            ("include_in_invoice", "=", True),
        ]
        if date_to:
            domain.append(("order_id.delivery_date", "<", str(date_to)))
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "jewelry.repair.material.line",
            "view_mode": "list",
            "domain": domain,
        }

    def action_view_services_month(self):
        self.ensure_one()
        return self._get_service_line_action(self.date_from, None, _("Services This Month"))

    def action_view_materials_month(self):
        self.ensure_one()
        return self._get_material_line_action(self.date_from, None, _("Materials This Month"))

    def action_view_services_prev_month(self):
        self.ensure_one()
        return self._get_service_line_action(self.date_prev_from, self.date_prev_to, _("Services Last Month"))

    def action_view_materials_prev_month(self):
        self.ensure_one()
        return self._get_material_line_action(self.date_prev_from, self.date_prev_to, _("Materials Last Month"))

    @api.model
    def action_open_dashboard(self):
        today = fields.Date.today()
        month_start = today.replace(day=1)
        if today.month == 1:
            prev_month_start = today.replace(year=today.year - 1, month=12, day=1)
        else:
            prev_month_start = today.replace(month=today.month - 1, day=1)

        Order = self.env["jewelry.repair.order"]

        delivered_month = Order.search([
            ("state", "=", "delivered"),
            ("delivery_date", ">=", str(month_start)),
        ])
        delivered_prev = Order.search([
            ("state", "=", "delivered"),
            ("delivery_date", ">=", str(prev_month_start)),
            ("delivery_date", "<", str(month_start)),
        ])
        in_progress = Order.search([("state", "=", "in_progress")])
        ready = Order.search([("state", "in", ["ready", "ready_for_delivery"])])
        waiting = Order.search([("state", "=", "draft")])

        from collections import defaultdict

        def _services(orders):
            return sum(sum(o.service_line_ids.mapped("subtotal")) for o in orders)

        def _materials(orders):
            return sum(
                sum(o.material_line_ids.filtered(lambda l: l.include_in_invoice).mapped("subtotal"))
                for o in orders
            )

        def _service_breakdown(orders):
            groups = {}
            for order in orders:
                for line in order.service_line_ids:
                    key = line.product_id.id or 0
                    if key not in groups:
                        groups[key] = {
                            "service_name": line.product_id.name or "—",
                            "product_id": line.product_id.id or False,
                            "qty": 0.0, "orders": set(), "amount": 0.0, "outsource": 0.0,
                        }
                    groups[key]["qty"] += line.total_quantity
                    groups[key]["orders"].add(order.id)
                    groups[key]["amount"] += line.subtotal
                    groups[key]["outsource"] += line.outsource_cost
            return sorted([
                {
                    "service_name": v["service_name"],
                    "product_id": v["product_id"],
                    "quantity": v["qty"],
                    "order_count": len(v["orders"]),
                    "amount": v["amount"],
                    "outsource_cost": v["outsource"],
                }
                for v in groups.values()
            ], key=lambda x: -x["amount"])

        def _material_breakdown(orders):
            groups = {}
            for order in orders:
                for line in order.material_line_ids.filtered(lambda l: l.include_in_invoice):
                    key = (line.alloy_id.id or 0, line.product_id.id or 0)
                    if key not in groups:
                        groups[key] = {
                            "alloy_name": line.alloy_id.name if line.alloy_id else (line.product_id.name or "—"),
                            "alloy_id": line.alloy_id.id or False,
                            "product_id": line.product_id.id or False,
                            "qty": 0.0, "orders": set(), "amount": 0.0,
                        }
                    groups[key]["qty"] += line.weight or 0.0
                    groups[key]["orders"].add(order.id)
                    groups[key]["amount"] += line.subtotal
            return sorted([
                {
                    "alloy_name": v["alloy_name"],
                    "alloy_id": v["alloy_id"],
                    "product_id": v["product_id"],
                    "quantity": v["qty"],
                    "order_count": len(v["orders"]),
                    "amount": v["amount"],
                }
                for v in groups.values()
            ], key=lambda x: -x["amount"])

        def _client_breakdown(orders):
            groups = {}
            for order in orders:
                key = order.partner_id.id if order.partner_id else 0
                name = order.partner_id.name or "—"
                if key not in groups:
                    groups[key] = {"partner_name": name, "orders": set(), "amount": 0.0, "services": {}, "materials": {}}
                groups[key]["orders"].add(order.id)
                groups[key]["amount"] += order.amount_total
                for line in order.service_line_ids:
                    skey = line.product_id.id or 0
                    if skey not in groups[key]["services"]:
                        groups[key]["services"][skey] = {
                            "service_name": line.product_id.name or "—",
                            "product_id": line.product_id.id or False,
                            "qty": 0.0, "orders": set(), "amount": 0.0,
                        }
                    groups[key]["services"][skey]["qty"] += line.total_quantity
                    groups[key]["services"][skey]["orders"].add(order.id)
                    groups[key]["services"][skey]["amount"] += line.subtotal
                for line in order.material_line_ids.filtered(lambda l: l.include_in_invoice):
                    mkey = (line.alloy_id.id or 0, line.product_id.id or 0)
                    if mkey not in groups[key]["materials"]:
                        groups[key]["materials"][mkey] = {
                            "alloy_name": line.alloy_id.name if line.alloy_id else (line.product_id.name or "—"),
                            "alloy_id": line.alloy_id.id or False,
                            "product_id": line.product_id.id or False,
                            "qty": 0.0, "orders": set(), "amount": 0.0,
                        }
                    groups[key]["materials"][mkey]["qty"] += line.weight or 0.0
                    groups[key]["materials"][mkey]["orders"].add(order.id)
                    groups[key]["materials"][mkey]["amount"] += line.subtotal
            result = []
            for v in sorted(groups.values(), key=lambda x: -x["amount"]):
                result.append({
                    "partner_name": v["partner_name"],
                    "order_count": len(v["orders"]),
                    "amount": v["amount"],
                    "services": sorted([
                        {"service_name": sv["service_name"], "product_id": sv["product_id"],
                         "quantity": sv["qty"], "order_count": len(sv["orders"]), "amount": sv["amount"]}
                        for sv in v["services"].values()
                    ], key=lambda x: -x["amount"]),
                    "materials": sorted([
                        {"alloy_name": mv["alloy_name"], "alloy_id": mv["alloy_id"], "product_id": mv["product_id"],
                         "quantity": mv["qty"], "order_count": len(mv["orders"]), "amount": mv["amount"]}
                        for mv in v["materials"].values()
                    ], key=lambda x: -x["amount"]),
                })
            return result

        payments_month = self.env["account.payment"].sudo().search([
            ("payment_type", "=", "inbound"),
            ("state", "=", "posted"),
            ("date", ">=", str(month_start)),
            ("company_id", "=", self.env.company.id),
        ])
        paid_month = sum(payments_month.mapped("amount"))

        payments_prev_month = self.env["account.payment"].sudo().search([
            ("payment_type", "=", "inbound"),
            ("state", "=", "posted"),
            ("date", ">=", str(prev_month_start)),
            ("date", "<", str(month_start)),
            ("company_id", "=", self.env.company.id),
        ])
        paid_prev_month = sum(payments_prev_month.mapped("amount"))

        record = self.sudo().create({
            "date_from": month_start,
            "date_prev_from": prev_month_start,
            "date_prev_to": month_start,
            "waiting_amount": sum(waiting.mapped("amount_total")),
            "waiting_count": len(waiting),
            "in_progress_amount": sum(in_progress.mapped("amount_total")),
            "in_progress_count": len(in_progress),
            "ready_amount": sum(ready.mapped("amount_total")),
            "ready_count": len(ready),
            "revenue_month_services": _services(delivered_month),
            "revenue_month_materials": _materials(delivered_month),
            "revenue_month": sum(delivered_month.mapped("amount_total")),
            "revenue_month_count": len(delivered_month),
            "paid_month": paid_month,
            "revenue_prev_month_services": _services(delivered_prev),
            "revenue_prev_month_materials": _materials(delivered_prev),
            "revenue_prev_month": sum(delivered_prev.mapped("amount_total")),
            "revenue_prev_month_count": len(delivered_prev),
            "paid_prev_month": paid_prev_month,
        })

        ServiceLine = self.env["jewelry.repair.kpi.service.line"].sudo()
        MaterialLine = self.env["jewelry.repair.kpi.material.line"].sudo()
        ClientLine = self.env["jewelry.repair.kpi.client.line"].sudo()
        ClientServiceLine = self.env["jewelry.repair.kpi.client.service.line"].sudo()
        ClientMaterialLine = self.env["jewelry.repair.kpi.client.material.line"].sudo()

        for row in _service_breakdown(delivered_month):
            ServiceLine.create({"dashboard_id": record.id, **row})
        for row in _material_breakdown(delivered_month):
            MaterialLine.create({"dashboard_id": record.id, **row})
        for row in _client_breakdown(delivered_month):
            services = row.pop("services")
            materials = row.pop("materials")
            cl = ClientLine.create({"dashboard_id": record.id, **row})
            for srow in services:
                ClientServiceLine.create({"client_line_id": cl.id, **srow})
            for mrow in materials:
                ClientMaterialLine.create({"client_line_id": cl.id, **mrow})
        for row in _service_breakdown(delivered_prev):
            ServiceLine.create({"dashboard_prev_id": record.id, **row})
        for row in _material_breakdown(delivered_prev):
            MaterialLine.create({"dashboard_prev_id": record.id, **row})
        for row in _client_breakdown(delivered_prev):
            services = row.pop("services")
            materials = row.pop("materials")
            cl = ClientLine.create({"dashboard_prev_id": record.id, **row})
            for srow in services:
                ClientServiceLine.create({"client_line_id": cl.id, **srow})
            for mrow in materials:
                ClientMaterialLine.create({"client_line_id": cl.id, **mrow})

        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.repair.kpi.dashboard",
            "res_id": record.id,
            "view_mode": "form",
            "target": "current",
            "name": _("Financial Dashboard"),
        }

    def action_print_dashboard(self):
        self.ensure_one()
        return self.env.ref("jewelry_repair_base.action_report_kpi_dashboard").report_action(self)
