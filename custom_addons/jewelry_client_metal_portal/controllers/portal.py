from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.jewelry_repair_portal.controllers.portal import JewelryRepairPortal

TRANSACTIONS_PER_PAGE = 20


class JewelryClientMetalPortal(JewelryRepairPortal):

    def _get_metal_accounts(self):
        """Active metal accounts of the clients this portal user may see them for."""
        partner_ids = request.env['jewelry.portal.access'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('show_metal_account', '=', True),
        ]).mapped('partner_id').ids
        Account = request.env['jewelry.client.metal.account'].sudo()
        if not partner_ids:
            return Account.browse()
        return Account.search([
            ('partner_id', 'in', partner_ids),
            ('active', '=', True),
        ])

    def _get_metal_debit_detail(self, transaction):
        """Reference breakdown of a repair debit.

        Returns the alloys billed to the client, their fine equivalent, and how the
        debit splits between the metal itself and the services it spilled over into.
        """
        if (
            transaction.transaction_type != 'debit_repair'
            or transaction.source_model != 'jewelry.repair.order'
            or not transaction.source_res_id
        ):
            return {}

        order = request.env['jewelry.repair.order'].sudo().browse(
            transaction.source_res_id
        ).exists()
        if not order:
            return {}

        detail = {'order': order}

        billing_line = order.billing_batch_id.line_ids.filtered(
            lambda bl: bl.order_id == order
        )[:1]
        if not billing_line:
            return detail

        alloy_weights = {}
        for material in order.material_line_ids.filtered(
            lambda l: l.include_in_invoice and l.alloy_id
        ):
            alloy_weights.setdefault(material.alloy_id, 0.0)
            alloy_weights[material.alloy_id] += (
                (material.weight or 0.0) + (material.weight_loss or 0.0)
            )

        pricing_fine = billing_line.total_pricing_fine
        debit_fine = billing_line.client_metal_debit_fine
        detail.update({
            'alloy_weights': [
                {'alloy': alloy.display_name, 'weight': weight}
                for alloy, weight in alloy_weights.items()
            ],
            'pricing_fine': pricing_fine,
            'metal_fine': min(debit_fine, pricing_fine),
            'service_fine': max(0.0, debit_fine - pricing_fine),
        })
        return detail

    def _prepare_metal_section(self, account, page):
        """One account block: paged statement rows with a running balance."""
        transactions = account.transaction_ids.filtered(
            lambda t: t.state == 'posted'
        ).sorted(key=lambda t: (t.transaction_date, t.id))

        balance = 0.0
        rows = []
        for transaction in transactions:
            balance += transaction.weight_fine
            rows.append({'transaction': transaction, 'balance': balance})
        rows.reverse()

        pager = portal_pager(
            url='/my/repairs',
            url_args={'tab': 'metal', 'account_id': account.id},
            total=len(rows),
            page=page,
            step=TRANSACTIONS_PER_PAGE,
        )
        offset = (pager['page']['num'] - 1) * TRANSACTIONS_PER_PAGE
        page_rows = rows[offset:offset + TRANSACTIONS_PER_PAGE]
        type_labels = dict(
            account.transaction_ids._fields['transaction_type']._description_selection(request.env)
        )
        for row in page_rows:
            row['detail'] = self._get_metal_debit_detail(row['transaction'])
            row['type_label'] = type_labels.get(row['transaction'].transaction_type)

        return {
            'account': account,
            'rows': page_rows,
            'pager': pager if len(rows) > TRANSACTIONS_PER_PAGE else None,
        }

    def _get_order_metal_split(self, order):
        """Order amount before and after the metal debited at billing.

        Orders billed without a metal debit keep the plain order total, so nothing
        changes for them.
        """
        plain = {
            'amount_before_metal': order.amount_total,
            'metal_reduction': 0.0,
            'amount_to_pay': order.amount_total,
        }
        billing_line = order.billing_batch_id.line_ids.filtered(
            lambda bl: bl.order_id == order
        )[:1]
        if not billing_line or not billing_line.metal_amount_reduction:
            return plain
        return {
            'amount_before_metal': billing_line.order_amount_total,
            'metal_reduction': billing_line.metal_amount_reduction,
            'amount_to_pay': billing_line.effective_amount_total,
        }

    def portal_repair_detail(self, order_id, **kw):
        response = super().portal_repair_detail(order_id, **kw)
        order = response.qcontext.get('order')
        if order:
            response.qcontext.update(self._get_order_metal_split(order))
        return response

    def portal_my_repairs(self, page=1, tab='active', **kw):
        accounts = self._get_metal_accounts()

        if tab == 'metal' and accounts:
            try:
                paged_account_id = int(kw.get('account_id') or 0)
            except ValueError:
                paged_account_id = 0
            sections = [
                self._prepare_metal_section(
                    account, page if account.id == paged_account_id else 1
                )
                for account in accounts
            ]
            return request.render('jewelry_repair_portal.portal_my_repairs', {
                'orders': request.env['jewelry.repair.order'].browse(),
                'tab': 'metal',
                'pager': None,
                'page_name': 'repair',
                'total_outstanding': 0.0,
                'advance_amount': 0.0,
                'net_to_pay': 0.0,
                'show_metal_account': True,
                'show_payment_statement': bool(self._get_statement_partners()),
                'metal_sections': sections,
                'effective_amounts': {},
            })

        response = super().portal_my_repairs(page=page, tab=tab, **kw)
        response.qcontext['show_metal_account'] = bool(accounts)
        response.qcontext['effective_amounts'] = {
            order.id: self._get_order_metal_split(order)['amount_to_pay']
            for order in response.qcontext.get('orders', [])
        }
        return response
