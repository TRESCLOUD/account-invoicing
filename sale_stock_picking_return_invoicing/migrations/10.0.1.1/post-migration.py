# -*- coding: utf-8 -*-
# Copyright 2018 Trescloud <http://trescloud.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
###################################################
from passlib.tests.utils import limit
'''
Archivo de migracion de Recalculo de cantidad entregada ventas
'''
###################################################
from openupgradelib import openupgrade

@openupgrade.logging()
def actualizar_lineas_orden_venta(env):
    '''
    Metodo calcular , cantidad a entregar, entregada, facturada, reembolsos ordenes de venta
    '''
    sale_order_line = env['sale.order.line'].search([])
    
    for line in sale_order_line:
        line.qty_delivered = line._get_delivered_qty()
        line._compute_qty_to_deliver()
        line._compute_qty_returned()
        line._get_to_invoice_qty()
        line._get_invoice_qty()
        
@openupgrade.migrate(use_env=True)
def migrate(env, version):
    cr = env.cr
    actualizar_lineas_orden_venta(env)
