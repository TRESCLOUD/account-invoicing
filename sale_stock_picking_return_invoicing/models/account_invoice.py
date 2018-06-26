# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round as round
from datetime import datetime
import odoo.addons.decimal_precision as dp
import re


class AccountInvoiceLine(models.Model):    
    _inherit = 'account.invoice.line'
    
    #HOOK AGREGADO POR TRESCLOUD
    def _get_anglo_saxon_price_unit_helper(self):
        '''
        Redefinimos el precio con el precio del PRIMER reingreso al sistema de stock
        (de forma nativa tomaba el precio promedio vigente)
        #TODO: Al implementar notas de credito sobre multiples devoluciones debería
        rehacerse la lógica para que genere un asiento en la cuenta puente por cada devolución.
        '''
        price = self.product_id.standard_price
        if self.invoice_id.type == 'out_refund' and self.refund_stock_move_ids:
            #NOTA: De momento funciona pues solo hay un refund_stock_move_ids
            price = self.refund_stock_move_ids[0].price_unit
        else:
            price = super(AccountInvoiceLine, self)._get_anglo_saxon_price_unit_helper()
        return price

    #Columns
    refund_stock_move_ids = fields.Many2many(
        comodel_name='stock.move', 
        string='Refund Stock Moves',
        copy=False,
        help="Related stock moves "
             "(only when it is a sale refund invoice generated from a sale order)."
        )
