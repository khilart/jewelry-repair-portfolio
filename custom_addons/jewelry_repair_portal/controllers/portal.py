from odoo import _
from odoo.exceptions import MissingError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

STATEMENT_ROWS_PER_PAGE = 20


class JewelryRepairPortal(CustomerPortal):

    def _get_allowed_partner_ids(self):
        """Return partner IDs accessible to the current portal user."""
        accesses = request.env['jewelry.portal.access'].sudo().search([
            ('user_id', '=', request.env.user.id),
        ])
        return accesses.mapped('partner_id').ids

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'repair_count' in counters:
            partner_ids = self._get_allowed_partner_ids()
            values['repair_count'] = request.env['jewelry.repair.order'].sudo().search_count([
                ('partner_id', 'in', partner_ids),
                ('state', 'not in', ['cancel']),
            ])
        return values

    @route(['/my/repairs', '/my/repairs/page/<int:page>'],
           type='http', auth='user', website=True)
    def portal_my_repairs(self, page=1, tab='active', **kw):
        partner_ids = self._get_allowed_partner_ids()
        Order = request.env['jewelry.repair.order'].sudo()
        statement_partners = self._get_statement_partners()

        if tab == 'statement' and statement_partners:
            try:
                paged_partner_id = int(kw.get('partner_id') or 0)
            except ValueError:
                paged_partner_id = 0
            sections = [
                self._prepare_statement_section(
                    partner, page if partner.id == paged_partner_id else 1
                )
                for partner in statement_partners
            ]
            return request.render('jewelry_repair_portal.portal_my_repairs', {
                'orders': Order.browse(),
                'tab': 'statement',
                'pager': None,
                'page_name': 'repair',
                'total_outstanding': 0.0,
                'advance_amount': 0.0,
                'net_to_pay': 0.0,
                'show_payment_statement': True,
                'statement_sections': sections,
                'currency': request.env.company.currency_id,
            })

        base_delivered = [
            ('partner_id', 'in', partner_ids),
            ('state', '=', 'delivered'),
        ]

        if tab == 'to_pay':
            all_delivered = Order.search(base_delivered, order='delivery_date desc, id desc')
            all_orders = all_delivered.filtered(
                lambda o: o.payment_status in ('unbilled', 'unpaid', 'partial')
            )
            seen_batch_ids = set()
            total_outstanding = 0.0
            for order in all_orders:
                if not order.billing_batch_id:
                    total_outstanding += order.amount_total
                elif order.billing_batch_id.id not in seen_batch_ids:
                    seen_batch_ids.add(order.billing_batch_id.id)
                    invoice = order.billing_batch_id.invoice_id
                    total_outstanding += invoice.amount_residual if invoice else sum(
                        o.amount_total for o in all_orders
                        if o.billing_batch_id.id == order.billing_batch_id.id
                    )
            ar_summaries = request.env['jewelry.repair.ar.summary'].sudo().search([
                ('partner_id', 'in', partner_ids),
            ])
            advance_amount = sum(ar_summaries.mapped('advance_amount'))
            net_to_pay = max(0.0, total_outstanding - advance_amount)
        elif tab == 'paid':
            all_delivered = Order.search(base_delivered, order='delivery_date desc, id desc')
            all_orders = all_delivered.filtered(lambda o: o.payment_status == 'paid')
            total_outstanding = 0
            advance_amount = 0.0
            net_to_pay = 0.0
        else:
            tab = 'active'
            all_orders = Order.search([
                ('partner_id', 'in', partner_ids),
                ('state', 'in', ['draft', 'in_progress', 'ready']),
            ], order='deadline_date asc, id asc')
            total_outstanding = 0
            advance_amount = 0.0
            net_to_pay = 0.0

        total = len(all_orders)
        offset = (page - 1) * 20

        pager = portal_pager(
            url='/my/repairs',
            url_args={'tab': tab},
            total=total,
            page=page,
            step=20,
        )

        orders = all_orders[offset:offset + 20]

        return request.render('jewelry_repair_portal.portal_my_repairs', {
            'orders': orders,
            'tab': tab,
            'pager': pager,
            'page_name': 'repair',
            'total_outstanding': total_outstanding,
            'advance_amount': advance_amount,
            'net_to_pay': net_to_pay,
            'show_payment_statement': bool(statement_partners),
        })

    def _get_statement_partners(self):
        """Clients this portal user may see the money statement for."""
        return request.env['jewelry.portal.access'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('show_payment_statement', '=', True),
        ]).mapped('partner_id')

    def _prepare_statement_section(self, partner, page):
        """One client block: paged ledger rows, newest first, and the closing balance."""
        rows = partner._jewelry_balance_statement()
        balance = rows[-1]['balance'] if rows else 0.0
        rows = list(reversed(rows))

        pager = portal_pager(
            url='/my/repairs',
            url_args={'tab': 'statement', 'partner_id': partner.id},
            total=len(rows),
            page=page,
            step=STATEMENT_ROWS_PER_PAGE,
        )
        offset = (pager['page']['num'] - 1) * STATEMENT_ROWS_PER_PAGE

        return {
            'partner': partner,
            'rows': rows[offset:offset + STATEMENT_ROWS_PER_PAGE],
            'balance': balance,
            'pager': pager if len(rows) > STATEMENT_ROWS_PER_PAGE else None,
        }

    @route(['/my/repairs/<int:order_id>'], type='http', auth='user', website=True)
    def portal_repair_detail(self, order_id, **kw):
        partner_ids = self._get_allowed_partner_ids()

        order = request.env['jewelry.repair.order'].sudo().search([
            ('id', '=', order_id),
            ('partner_id', 'in', partner_ids),
        ])

        if not order:
            raise MissingError(_("This repair order does not exist or you don't have access to it."))

        access = request.env['jewelry.portal.access'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('partner_id', '=', order.partner_id.id),
        ], limit=1)
        show_operations = access.show_operations if access else False
        collapse_new_product_services = access.collapse_new_product_services if access else False
        show_uninvoiced_gems = access.show_uninvoiced_gems if access else False
        show_delivery_weights = access.show_delivery_weights if access else False

        all_gems = order.gem_line_ids
        if show_uninvoiced_gems:
            gems_to_show = all_gems
        else:
            gems_to_show = all_gems.filtered(lambda g: g.include_in_invoice)
        cert_modals = gems_to_show.mapped('certificate_id')

        uninvoiced_gems_total = sum(
            all_gems.filtered(lambda g: not g.include_in_invoice).mapped('subtotal')
        )
        amount_to_pay = order.amount_total
        amount_full = order.amount_total + uninvoiced_gems_total

        area_groups = []
        if show_operations:
            ops = order.order_operation_ids.sorted(lambda op: (op.sequence, op.id))
            seen_areas = {}
            no_area_ops = []
            for op in ops:
                area = op.operation_id.area_id if op.operation_id else None
                if not area:
                    no_area_ops.append(op)
                    continue
                if area.id not in seen_areas:
                    seen_areas[area.id] = {'name': area.name, 'ops': [], 'sequence': area.sequence}
                seen_areas[area.id]['ops'].append(op)

            for area_data in sorted(seen_areas.values(), key=lambda a: a['sequence']):
                states = [op.state for op in area_data['ops']]
                if all(s == 'done' for s in states):
                    agg_state = 'done'
                elif any(s == 'in_progress' for s in states):
                    agg_state = 'in_progress'
                elif any(s == 'accepted' for s in states):
                    agg_state = 'accepted'
                elif any(s == 'ready' for s in states):
                    agg_state = 'ready'
                else:
                    agg_state = 'pending'
                area_groups.append({'name': area_data['name'], 'state': agg_state, 'is_area': True})

            for op in no_area_ops:
                area_groups.append({'name': op.name, 'state': op.state, 'is_area': False})

        return request.render('jewelry_repair_portal.portal_repair_detail', {
            'order': order,
            'page_name': 'repair',
            'show_operations': show_operations,
            'area_groups': area_groups,
            'collapse_new_product_services': collapse_new_product_services,
            'show_delivery_weights': show_delivery_weights,
            'gems_to_show': gems_to_show,
            'cert_modals': cert_modals,
            'amount_to_pay': amount_to_pay,
            'amount_full': amount_full,
        })
