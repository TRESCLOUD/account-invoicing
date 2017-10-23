# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ReturnPicking(models.TransientModel):
     _inherit = 'stock.return.picking'

     @api.model
     def default_get(self, fields):
         '''Get purchase order for lines.'''
         result = super(ReturnPicking, self).default_get(fields)
         try:
             for line in result['product_return_moves']:
                 assert line[0] == 0
                 move = self.env['stock.move'].browse(line[2]['move_id'])
                 line[2]['sale_line_id'] = (move.procurement_id.sale_line_id.id)
         except KeyError:
             pass
         return result


class ReturnPickingLine(models.TransientModel):
    _inherit = 'stock.return.picking.line'

    sale_line_id = fields.Many2one(comodel_name='sale.order.line',
        string='Sale order line',
        readonly=True)
