{
    "name": "Jewelry Repair Delivery",
    "version": "17.0.1.0.0",
    "summary": "Delivery documents for jewelry repair orders",
    "license": "LGPL-3",
    "depends": ["jewelry_repair_base"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir.rules.xml",
        "data/ir_sequence_data.xml",
        "reports/delivery_report.xml",
        "views/delivery_views.xml",
    ],
    "installable": True,
    "application": False,
}
