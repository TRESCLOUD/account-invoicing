# -*- coding: utf-8 -*-
# © 2017 Therp BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade

@openupgrade.logging()
def active_reprocess_sale_lines_qty(env):
    '''
    Metodo que reactiva el procesamiento de las lineas usando el cron ya existente
    '''
    env.cr.execute("""
        update sale_order set reprocess_lines = False;
        """)
    xml_data_cron = env['ir.model.data'].search([('name', '=', 'process_pending_action_compute_sale_line_qty'), ('module', '=', 'sale_stock_picking_return_invoicing')])
    if xml_data_cron:
        env['ir.cron'].browse(xml_data_cron[0].res_id).active = True
    else:
        raise "No existe el cron de reprocesamiento de catidad en las lineas de venta"    
    
@openupgrade.migrate(use_env=True)
def migrate(env, version):
    active_reprocess_sale_lines_qty(env)    
