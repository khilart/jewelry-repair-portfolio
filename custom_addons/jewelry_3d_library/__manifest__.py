{
    'name': 'Jewelry 3D Model Library',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing/Jewelry',
    'summary': '3D model library and manufacturing order templates for jewelry workshop',
    'depends': ['jewelry_repair_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/model_3d_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'jewelry_3d_library/static/src/css/model_3d.css',
            'jewelry_3d_library/static/src/js/model_3d_viewer.js',
            'jewelry_3d_library/static/src/xml/model_3d_viewer.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
