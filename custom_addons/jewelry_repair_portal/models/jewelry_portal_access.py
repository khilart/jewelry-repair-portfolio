from odoo import fields, models


class JewelryRepairOrderPortal(models.Model):
    """Restrict repair order visibility for portal users at ORM level."""
    _inherit = 'jewelry.repair.order'

    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.user.has_group('base.group_portal'):
            allowed_partner_ids = self.env['jewelry.portal.access'].sudo().search([
                ('user_id', '=', self.env.user.id),
            ]).mapped('partner_id').ids
            domain = [('partner_id', 'in', allowed_partner_ids)] + list(domain)
        return super()._search(domain, offset=offset, limit=limit, order=order)


class JewelryPortalAccess(models.Model):
    _name = 'jewelry.portal.access'
    _description = 'Jewelry Portal Client Access'
    _rec_name = 'partner_id'

    user_id = fields.Many2one(
        'res.users',
        string='Portal User',
        required=True,
        ondelete='cascade',
        domain=[('share', '=', True)],
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        ondelete='cascade',
    )
    show_operations = fields.Boolean(
        string='Show Operations',
        default=False,
        help='If enabled, the client will see the operation route and status on each repair order.',
    )
    collapse_new_product_services = fields.Boolean(
        string='Collapse New Product Services',
        default=False,
        help='If enabled, services for new product manufacturing orders are shown as a single line instead of individually.',
    )
    show_uninvoiced_gems = fields.Boolean(
        string='Show Uninvoiced Gems',
        default=False,
        help='If enabled, gems not billed to the client are also shown in the portal order breakdown.',
    )
    show_delivery_weights = fields.Boolean(
        string='Show Delivery Weights',
        default=False,
        help='If enabled, the client will see item, metal and gem weights measured at delivery on the order detail page.',
    )
    show_payment_statement = fields.Boolean(
        string='Show Payment Statement',
        default=False,
        help='If enabled, the client will see a money statement: delivered orders as debit, '
             'payments as credit, and the balance after each row.',
    )

    _sql_constraints = [
        ('unique_user_partner', 'UNIQUE(user_id, partner_id)',
         'This client is already granted to this portal user.'),
    ]
