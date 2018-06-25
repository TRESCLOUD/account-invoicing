# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime, timedelta
import time
import re

class ReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"
     
    @api.model
    def default_get(self, fields):
        '''
        Asigna un valor por defecto al campo tecnico is_sale_return 
        para ocultar o mostrar los campos relacionados
        '''
        res = super(ReturnPicking, self).default_get(fields)
        picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
        is_sale_return = False
        if any(line.procurement_id.sale_line_id for line in picking.move_lines):
            is_sale_return = True
        res['is_sale_return'] = is_sale_return
        return res
    
#     @api.onchange('refund_invoice_state')
#     def onchange_refund_invoice_state(self):
#         '''
#         Al cambiar el invoice state reseteamos el valor de los campos nativos de v10 para que tengan un valor equivalente
#         '''
#         vals = {'value': {},'warning':{},'domain':{}}
#         to_refund_so = False
#         if self.refund_invoice_state in ['2binvoiced']:
#             to_refund_so = True
#         for move in self.product_return_moves:
#             move.to_refund_so = to_refund_so
    
    @api.multi
    def _create_returns(self):
        '''
        Pasamos el valor seleccionado en la variable 'refund_invoice_state' del wizard al picking
        (El valor to_refund_so ya fue pasado en cada linea)
        '''
        new_picking_id, pick_type_id = super(ReturnPicking, self)._create_returns()
        new_picking = self.env['stock.picking'].browse([new_picking_id])
        new_picking.refund_invoice_state = self.refund_invoice_state
        return new_picking_id, pick_type_id
    
    is_sale_return = fields.Boolean(
        'Is return',
        help='Technical field, to hide/show refund option, indicates when a delivery is a sales return'
        )
    refund_invoice_state = fields.Selection(
            [
             ('2binvoiced','Emitir Nota de Crédito'),
             ('none','No emitir Nota de Crédito'),
             ],
        string="Emision Nota Credito",
        required=True,
        default='none',
        track_visibility='onchange',
        help='''En las devoluciones en ventas indica si:\n
                - Se debe emitir una nota de crédito
                - No se debe emitir una nota de crédito'''
        )
    