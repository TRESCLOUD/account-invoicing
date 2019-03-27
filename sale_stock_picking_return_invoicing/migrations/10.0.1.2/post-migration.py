# -*- coding: utf-8 -*-
# Copyright 2019 Trescloud <http://trescloud.com>
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openupgradelib import openupgrade
import logging

_logger = logging.getLogger(__name__)

@openupgrade.logging()
def update_to_refund_so(env): 
    '''
    Este metodo setea el campo to_refund_so de los movimientos de devolucion de 
    compras, ventas e importaciones en base al campo refund_invoice_state.
    '''
    _logger.info(u'Set campo to_refund_so...')
    #update select: actualiza todos los movimientos del stock picking
    #que el campo refund_invoice_state sea '2binvoiced' o 'invoiced'
    env.cr.execute('''
        UPDATE stock_move
        SET to_refund_so = true
        FROM (
            SELECT sm.id from stock_move sm join
                   stock_picking sp on sm.picking_id = sp.id
            WHERE sp.refund_invoice_state in ('2binvoiced','invoiced')
            and  to_refund_so =  false
        ) AS m
        WHERE stock_move.id = m.id;
    ''')
    _logger.info(u'Fin set campo to_refund_so...')

@openupgrade.migrate(use_env=True)
def migrate(env, version):
    update_to_refund_so(env)    
