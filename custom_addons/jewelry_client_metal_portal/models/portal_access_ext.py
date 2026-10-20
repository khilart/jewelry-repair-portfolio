from odoo import fields, models


class JewelryPortalAccess(models.Model):
    _inherit = 'jewelry.portal.access'

    show_metal_account = fields.Boolean(
        string='Show Metal Account',
        default=False,
        help='If enabled, the client will see a Metal Account tab with the statement of '
             'metal deposits and repair debits.',
    )
