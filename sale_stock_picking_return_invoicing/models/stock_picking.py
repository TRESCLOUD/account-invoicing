# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime, timedelta
import time
import re


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.onchange('refund_invoice_state')
    def onchange_refund_invoice_state(self):
        '''
        Al cambiar el invoice state reseteamos el valor de los campos nativos de v10 para que tengan un valor equivalente
        '''
        vals = {'value': {},'warning':{},'domain':{}}
        to_refund_so = False
        if self.refund_invoice_state in ['2binvoiced','invoiced']:
            to_refund_so = True
        for move in self.move_lines:
            move.to_refund_so = to_refund_so
        return {
            'warning': {
                'title': _('Advertencia'), 
                'message': _('El cambio será registrado, tenga presente que es su responsabilidad verificar la emisión de notas de crédito previo a realizar este cambio'),},
             }
    
    @api.multi
    def action_refund_invoice(self, grouped=False, final=False):
        '''
        Crea una nota de credito de cliente a partir de una devolucion en ventas
        basado en el codigo de action_invoice_create
        @grouped por implementar
        @final por implementar
        '''
        self.ensure_one() #al momento esta implementado para un solo documento
        if not self.is_sale_return:
            raise ValidationError(u'Desde este boton solo se puede emitir notas de credito para DEVOLUCIONES EN VENTAS, '
                                  u'para COMPRAS aplaste el boton "Notas de Credito" de la orden de compra')
        if self.refund_invoice_state not in ['2binvoiced']:
            raise ValidationError(u'Solo se puede emitir notas de credito para devoluciones pendientes')
        #obtenemos las ventas
        sale_orders = self.move_lines.mapped('procurement_id').mapped('sale_line_id').mapped('order_id')
        pos_orders = False
        if self.env['ir.module.module'].sudo().search([('name','=','point_of_sale'),('state','=','installed')]):
            #si el TPV esta instalado evaluamos si el picking es de tpv
            pos_orders = self.env['pos.order'].search([('picking_id','=',self.move_lines[0].origin_returned_move_id.picking_id.id)])
        if not sale_orders and not pos_orders:
            raise ValidationError(u'Esta devolución no está asociada a una una venta')
        if sale_orders and len(sale_orders)!=1:
            raise ValidationError(u'Esta devolución está asociada a multiples ventas, solo se puede emitir devoluciones de una venta')
        orders = sale_orders or pos_orders
        order = orders[0] #TODO implementar para un picking que sirve a multiples ordenes de venta
        #preparamos valores por defecto
        ctx = self._context.copy()
        ctx.update({'type':'out_refund'})
        if sale_orders:
            invoice_ids = order.invoice_ids.filtered(lambda x: x.type == 'out_invoice' and x.state not in ('cancel','draft')).mapped('id')
            if not invoice_ids:
                raise ValidationError(u'No se ha encontrado una factura de venta asociada')
            ctx.update({'default_invoice_rectification_id': invoice_ids[0] if invoice_ids else []})
            inv_data = order.with_context(ctx)._prepare_invoice()
            refund_invoice = self.env['account.invoice'].with_context(ctx).create(inv_data)
            for move in self.move_lines:
                ctx.update({'refund_move_ids' : move.ids}) #usado en _prepare_invoice_line para enlazar la NC al stock.move
                line = move.procurement_id.sale_line_id
                line.with_context(ctx).invoice_line_create(refund_invoice.id, move.product_uom_qty)
        elif pos_orders:
            invoice_ids = order.invoice_id.filtered(lambda x: x.type == 'out_invoice' and x.state not in ('cancel','draft'))
            if not invoice_ids:
                raise ValidationError(u'No se ha encontrado una factura de venta asociada')
            ctx.update({'default_invoice_rectification_id': invoice_ids[0] if invoice_ids else []})
            #el _prepare_refund no deberia requerir datos por contexto!
            inv_data = self.env['account.invoice'].with_context(ctx)._prepare_refund(invoice_ids[0])
            refund_invoice = self.env['account.invoice'].with_context(ctx).create(inv_data)
        message = _("Esta Nota de Credito ha sido creada desde : <a href=# data-oe-model=stock.picking data-oe-id=%d>%s</a>") % (self.id, self.display_name)
        refund_invoice.message_post(body=message)
        refund_invoice.compute_taxes()
        refund_invoice._finish_invoice_creation() #Metodo core de Trescloud para completar calculos finales
        self.refund_invoice_state = 'invoiced'
        #preparamos la respuesta en vista
        action = self.env.ref('account.action_invoice_tree1')
        result = action.read()[0]
        result['domain']= [('type', '=', ('out_refund')),('partner_id','=', order.partner_id.commercial_partner_id.id)]
        result['context'] = {
            'type': 'out_refund',
            'default_sale_id': order.id if sale_orders else False,
        }
        #TODO: Implementar memoria para saber que NCs estan asociadas a cada devolucion
        #hasta eso se reescribe la variable refunds para que no entre al if
        #refunds = order.invoice_ids.filtered(lambda x: x.type == 'out_refund')
        refunds = refund_invoice
        if len(refunds) == 1:
            result['views'] = [(order.with_context(ctx).env.ref('account.invoice_form').id, 'form')]
            result['res_id'] = refunds.id
        else:
            result['domain'] = [('id', 'in', refunds.ids)]
        return result
    
    @api.one
    @api.depends('move_lines.origin_returned_move_id')
    def _compute_is_sale_return(self):
        '''
        - Cuando las lineas son de DEVOLUCIONES de VENTAS entonces la cabecera se marca como devolucion
        - Cuando las devoluciones son sobre ordenes de tpv
        '''
        is_return = False
        is_sale = False #si el movimiento esta asociado a una venta
        if self.location_id.usage in ['customer']:
            if any(line.origin_returned_move_id for line in self.move_lines):
                is_return = True
                if any(line.procurement_id.sale_line_id for line in self.move_lines):
                    #Devoluciones de ordenes de venta
                    is_sale = True
                elif self.env['ir.module.module'].suspend_security().search([('name','=','point_of_sale'),('state','=','installed')]):
                    #si el TPV esta instalado evaluamos si el picking es de tpv
                    if self.env['pos.order'].search([('picking_id','=',self.move_lines[0].origin_returned_move_id.picking_id.id)]):
                        #Devoluciones de ordenes de punto de venta, las buscamos
                        #en base al picking de la devolución de la primera línea
                        is_sale = True
        self.is_sale_return = is_return and is_sale
        
    is_sale_return = fields.Boolean(
        'Is return',
        compute='_compute_is_sale_return',
        compute_sudo=True,
        help='Technical field, to hide/show refund option, indicates when a delivery is a sales return',
        )
    
    refund_invoice_state = fields.Selection(
            [('invoiced','Emitida'),
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
    