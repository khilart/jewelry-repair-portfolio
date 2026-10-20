{
    "name": "Jewelry Repair Labels",
    "version": "17.0.1.0.0",
    "summary": "Order labels with QR code for narrow thermal label printers",
    "license": "LGPL-3",
    "depends": ["jewelry_repair_base", "barcodes"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/repair_order_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "jewelry_repair_label/static/src/js/label_printer.js",
            "jewelry_repair_label/static/src/js/label_print_action.js",
            "jewelry_repair_label/static/src/js/printer_picker.js",
            "jewelry_repair_label/static/src/js/order_scan_list.js",
            "jewelry_repair_label/static/src/xml/label_print_action.xml",
            "jewelry_repair_label/static/src/xml/printer_picker.xml",
        ],
    },
    "external_dependencies": {"python": ["qrcode", "PIL"]},
    "installable": True,
}
