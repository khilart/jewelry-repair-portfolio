from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    weight_tracking_mode = fields.Selection(
        [
            ("disabled", "Disabled"),
            ("new_product_only", "New Products Only"),
            ("all", "All Orders"),
        ],
        string="Weight Tracking Mode",
        default="all",
        config_parameter="jewelry_repair_base.weight_tracking_mode",
        help="Controls whether masters are asked to weigh items before each operation "
             "and whether metal loss by area is calculated.",
    )
    weight_entry_by = fields.Selection(
        [
            ("master", "Master (wizard on Accept Item)"),
            ("manager", "Manager (editable in order table)"),
        ],
        string="Weight Entry By",
        default="master",
        config_parameter="jewelry_repair_base.weight_entry_by",
        help="Master: weight is entered via a wizard when the master clicks Accept Item.\n"
             "Manager: no wizard for the master; manager enters weight directly in the operations table.",
    )
