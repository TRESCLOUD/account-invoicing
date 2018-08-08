# -*- coding: utf-8 -*-
# © 2017 Therp BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade

@openupgrade.logging()
def deactive_reprocess_sale_lines_qty(env):
    '''
    Metodo que desactiva el procesamiento de las lineas del cron ya existente
    Se hace de esta forma para mantener los scripts de migracion anteriores
    '''
    xml_data_cron = env['ir.model.data'].search([('name', '=', 'process_pending_action_compute_sale_line_qty'), ('module', '=', 'sale_stock_picking_return_invoicing')])
    if xml_data_cron:
        env['ir.cron'].browse(xml_data_cron[0].res_id).active = False
    
@openupgrade.migrate(use_env=True)
def migrate(env, version):
    deactive_reprocess_sale_lines_qty(env)    
