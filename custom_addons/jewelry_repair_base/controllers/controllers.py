# -*- coding: utf-8 -*-
# from odoo import http


# class JewelryRepairBase(http.Controller):
#     @http.route('/jewelry_repair_base/jewelry_repair_base', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/jewelry_repair_base/jewelry_repair_base/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('jewelry_repair_base.listing', {
#             'root': '/jewelry_repair_base/jewelry_repair_base',
#             'objects': http.request.env['jewelry_repair_base.jewelry_repair_base'].search([]),
#         })

#     @http.route('/jewelry_repair_base/jewelry_repair_base/objects/<model("jewelry_repair_base.jewelry_repair_base"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('jewelry_repair_base.object', {
#             'object': obj
#         })

