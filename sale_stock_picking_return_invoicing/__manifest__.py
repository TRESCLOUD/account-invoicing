# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale Stock Picking Return Invoicing',
    'version': '10.0.1.4',
    'category': 'Sales',
    'description': '''
        Característica: 
            - Agrega una opción para crear notas de crédito desde órdenes de venta.
        
        Autores:
            Ing. Andres Calle
            Ing. Víctor Salazar
    ''',
    'author': 'TRESCLOUD CIA LTDA',
    'maintainer': 'TRESCLOUD CIA. LTDA.',
    'website': 'http://www.trescloud.com',
    'license': 'AGPL-3',
    'depends': [
         'sale',
         'sale_stock'
    ],    
    'data': [
        #Cron
        'data/ir_cron_scheduler_data.xml',
        #Data
        'views/sale_view.xml',
        'views/account_invoice_view.xml',
        'views/stock_picking_view.xml',
        'views/stock_return_picking_view.xml',
    ],
    'installable': True
}
