{
    'name': 'Jewelry Client Metal Portal',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing/Jewelry',
    'summary': 'Client metal account statement on the customer portal',
    'depends': ['jewelry_repair_portal', 'jewelry_client_metal_accounts'],
    'data': [
        'views/portal_access_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
