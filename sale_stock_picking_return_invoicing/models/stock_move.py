# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    #Columns
    refund_invoice_line_ids = fields.Many2many(
        comodel_name='account.invoice.line', 
        string='Invoice Lines',
        copy=False,
        help="Related invoice lines "
             "(only when it is a sale refund invoice generated from a sale order)."
        )