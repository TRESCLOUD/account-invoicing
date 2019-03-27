# -*- coding: utf-8 -*-
# Copyright 2019 Trescloud <http://trescloud.com>
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openupgradelib import openupgrade

@openupgrade.logging()
def stock_return_picking_rename_invoice_state(env):
    """
    Copiamos los valores de invoice_state a refund_invoice_state, siempre que
    el campo invoice_state exista en la base de datos.
    :param env:
    """
    if openupgrade.column_exists(env.cr, 'stock_picking', 'invoice_state'):
        #backups
        openupgrade.copy_columns(env.cr, {'stock_picking': [('refund_invoice_state', 'refund_inv_state_backup', None)]})
        env.cr.execute("""
                UPDATE stock_picking SET
                refund_invoice_state = invoice_state
                where refund_invoice_state != invoice_state;
            """)

@openupgrade.migrate(use_env=True)
def migrate(env, version):
    stock_return_picking_rename_invoice_state(env)

