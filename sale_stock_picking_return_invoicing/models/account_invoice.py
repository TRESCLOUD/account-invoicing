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
    
    #Columns
    refund_stock_move_ids = fields.Many2many(
        comodel_name='stock.move', 
        string='Refund Stock Moves',
        copy=False,
        help="Related stock moves "
             "(only when it is a sale refund invoice generated from a sale order)."
        )
