{
    "name": "Jewelry Client Metal Accounts",
    "version": "17.0.1.0.0",
    "summary": "Client metal accounts for jewelry repair workshop",
    "license": "LGPL-3",
    "depends": ["jewelry_repair_base", "jewelry_metal_accounting", "jewelry_repair_billing"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir.rules.xml",
        "data/ir_sequence_data.xml",
        "views/client_metal_account_views.xml",
        "views/metal_receipt_views.xml",
        "views/material_line_ext_views.xml",
        "views/billing_ext_views.xml",
        "reports/order_card_report.xml",
    ],
    "installable": True,
    "application": False,
}
