from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        if self.env.context.get('repair_service_search') and not order:
            order = 'sequence asc, name asc'
        return super()._name_search(name=name, domain=domain, operator=operator, limit=limit, order=order)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    repair_service_ok = fields.Boolean(
        string="Available for Repair Services",
        help="Allows this product to be selected as a commercial service in jewelry repair orders.",
    )
    repair_material_ok = fields.Boolean(
        string="Available for Repair Materials",
        help="Allows this product to be selected as a material or spare part in jewelry repair orders.",
    )
    repair_material_requires_weight = fields.Boolean(
        string="Weight Required for Repair Materials",
        help="Requires weight to be entered when this product is used as a repair material.",
    )
    repair_material_default_invoice = fields.Boolean(
        string="Invoice by Default in Repairs",
        help="Pre-fills the repair material line to include this product in the client invoice.",
    )
    repair_material_default_consume = fields.Boolean(
        string="Consume from Stock by Default",
        default=True,
        help="Pre-fills the repair material line to consume this product from stock.",
    )
    repair_material_return_loss_percent = fields.Float(
        string="Returnable Loss Percent",
        default=10.0,
        help="Default percentage of returnable metal losses used for repair material pricing.",
    )
    repair_material_nonreturn_loss_percent = fields.Float(
        string="Non-returnable Loss Percent",
        default=3.0,
        help="Default percentage of non-returnable metal losses stored on the repair material product.",
    )
    repair_operation_id = fields.Many2one(
        "jewelry.repair.operation",
        string="Default Repair Operation",
        help="Default production operation used when this service product is added to a repair order.",
    )
    gem_pricing_type = fields.Selection(
        [
            ("fixed", "Fixed Price"),
            ("per_carat", "Price per Carat"),
        ],
        string="Gem Pricing Type",
        default="fixed",
        help="Fixed: price_unit is used as-is for the total quantity of stones.\n"
             "Per Carat: price_unit is the base price per carat; "
             "final price = price_unit × weight_ct per stone.",
    )
