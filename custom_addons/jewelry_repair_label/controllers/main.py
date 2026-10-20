# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class JewelryRepairLabel(http.Controller):
    def _order(self, order_id):
        order = request.env["jewelry.repair.order"].browse(order_id)
        order.check_access_rights("read")
        order.check_access_rule("read")
        return order

    @http.route(
        "/jewelry/repair/label/<int:order_id>.png", type="http", auth="user"
    )
    def label_png(self, order_id, **kwargs):
        order = self._order(order_id)
        return request.make_response(
            order.label_png(),
            [
                ("Content-Type", "image/png"),
                ("Cache-Control", "no-store"),
            ],
        )

    @http.route(
        "/jewelry/repair/label/<int:order_id>.tspl", type="http", auth="user"
    )
    def label_tspl(self, order_id, **kwargs):
        order = self._order(order_id)
        return request.make_response(
            order.label_tspl(),
            [
                ("Content-Type", "application/octet-stream"),
                (
                    "Content-Disposition",
                    'attachment; filename="%s.tspl"' % order.name,
                ),
            ],
        )
