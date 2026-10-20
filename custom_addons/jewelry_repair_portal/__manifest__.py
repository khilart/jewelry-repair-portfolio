{
    'name': 'Jewelry Repair Portal',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing/Jewelry',
    'summary': 'Client portal for jewelry repair orders',
    'depends': ['jewelry_repair_base', 'jewelry_repair_billing', 'portal'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/portal_templates.xml',
        'views/portal_access_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'jewelry_repair_portal/static/src/css/portal.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
