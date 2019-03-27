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
    picking_id = env['stock.picking'].search([])
    move_refund_ids = picking_id.mapped('move_lines')
    if move_refund_ids:
        _logger.info(u'Set campo to_refund_so...')
        count = 1
        for move in move_refund_ids:
            refund = False
            if move.picking_id.refund_invoice_state in ['2binvoiced','invoiced']:
                refund = True
            move.to_refund_so = refund
            _logger.info(u'ID  move: %s. %s de %s'%(move.id, count, len(move_refund_ids)))
            count += 1
    _logger.info(u'Fin set campo to_refund_so...')

@openupgrade.migrate(use_env=True)
def migrate(env, version):
    update_to_refund_so(env)    
