{
    "name": "Jewelry Repair Expenses",
    "version": "17.0.1.0.0",
    "summary": "Workshop expense tracking: quick expenses, vendor bills, P&L dashboard",
    "license": "LGPL-3",
    "depends": ["jewelry_repair_base", "jewelry_repair_delivery", "jewelry_repair_billing", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/expense_category_rules.xml",
        "data/ir_sequence_data.xml",
        "views/expense_views.xml",
        "views/kpi_dashboard_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
