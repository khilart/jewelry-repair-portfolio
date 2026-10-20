{
    "name": "Jewelry Repair — Telegram Notifications",
    "version": "17.0.1.0.0",
    "category": "Jewelry",
    "summary": "Telegram push notifications for repair order events",
    "depends": ["jewelry_repair_base"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/jewelry_repair_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
