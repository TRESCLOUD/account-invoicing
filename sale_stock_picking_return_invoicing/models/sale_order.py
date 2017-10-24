# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
import odoo.addons.decimal_precision as dp
from odoo.tools import float_is_zero


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('order_line.invoice_lines.invoice_id.state')
    def _compute_invoice_refund(self):
         '''
         Obtiene el número de notas de crédito
         '''
         for order in self:
             invoices = self.env['account.invoice']
             for line in order.order_line:
                 invoices |= line.invoice_lines.mapped('invoice_id').filtered(lambda x: x.type == 'out_refund')
             order.invoice_refund_count = len(invoices)
             
    @api.depends('state', 'order_line.invoice_status')
    def _get_invoiced(self):
        '''
        obtiene el número de facturas asociados a la orden de venta.
        '''
        super(SaleOrder, self)._get_invoiced()
        for order in self:
            invoice_ids = order.order_line.mapped('invoice_lines').mapped('invoice_id').filtered(lambda r: r.type in ['out_invoice'])
            order.update({
                'invoice_count': len(set(invoice_ids.ids)),
                'invoice_ids': invoice_ids.ids
            })
            
    @api.multi
    def action_view_invoice_refund(self):
        '''
        Metodo llamana a la funcion de crear notas de credito en ventas.
        '''
        action = self.env.ref('account.action_invoice_tree1')
        result = action.read()[0]
        refunds = self.invoice_ids.filtered(lambda x: x.type == 'out_refund')
        result['domain']= [('type', '=', ('out_refund')),('partner_id','=', self.partner_id.id)]
        result['context'] = {
            'type': 'out_refund',
            'default_sale_id': self.id
        }
        for order in self:
            create = False 
            for line in order.order_line:
                if line.qty_to_refund > 0:
                    create = True
                    break
            if create:
               ctx = self._context.copy()
               ctx.update({'type':'out_refund'})
               order.with_context(ctx).action_invoice_refund()
        if len(refunds) > 1:
            result['domain'] =  [('id', 'in', refunds.ids)]
        elif len(refunds) == 1:
            result['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            result['res_id'] = refunds.id
        return result

    @api.multi
    def action_view_invoice(self):
        '''
        Filtar las facturas de tipo out_invoice
        '''
        result = super(SaleOrder, self).action_view_invoice()
        invoices = self.invoice_ids.filtered(lambda x: x.type == 'out_invoice')
        if len(invoices) > 1:
            result['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            result['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            result['res_id'] = invoices.id
        return result
    
    @api.multi
    def action_invoice_refund(self, grouped=False, final=False):
        '''
        Crea las notas de credito asociadas a las orden de venta.
        basado en el codigo de action_invoice_create. no se realiza super por que el metodo 
        tiene la logica de crear las lineas de la factura si el qty_to_invoice es diferente de 0.
        '''
        inv_obj = self.env['account.invoice']
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        invoices = {}
        references = {}
        for order in self:
            group_key = order.id if grouped else (order.partner_invoice_id.id, order.currency_id.id)
            for line in order.order_line.filtered(lambda l: l.qty_to_refund > 0):
                if float_is_zero(line.qty_to_refund, precision_digits=precision):
                    continue
                if group_key not in invoices:
                    inv_data = order._prepare_invoice()
                    invoice = inv_obj.create(inv_data)
                    references[invoice] = order
                    invoices[group_key] = invoice
                elif group_key in invoices:
                    vals = {}
                    if order.name not in invoices[group_key].origin.split(', '):
                        vals['origin'] = invoices[group_key].origin + ', ' + order.name
                    if order.client_order_ref and order.client_order_ref not in invoices[group_key].name.split(', ') and order.client_order_ref != invoices[group_key].name:
                        vals['name'] = invoices[group_key].name + ', ' + order.client_order_ref
                    invoices[group_key].write(vals)
                if line.qty_to_refund > 0:
                    line.invoice_line_create(invoices[group_key].id, line.qty_to_refund)
                elif line.qty_to_refund < 0 and final:
                    line.invoice_line_create(invoices[group_key].id, line.qty_to_refund)
            if references.get(invoices.get(group_key)):
                if order not in references[invoices[group_key]]:
                    references[invoice] = references[invoice] | order
        if invoices:            
            if invoice:
                invoice.compute_taxes()
        return [inv.id for inv in invoices.values()]

    @api.multi
    def _prepare_invoice(self):
        '''
        se actualiza la lineas de la factura para que seade tipo notas de credito.
        el core en su codigo esta quemado el tipo out_invoice.
        '''
        res = super(SaleOrder, self)._prepare_invoice()
        type = self._context.get('type',False)
        if type == 'out_refund':
            res.update({'type':'out_refund'})
            #diario
            journal_domain = [
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id)
            ]
            journal = self.env['account.journal'].search(journal_domain, limit=1)
            if journal:
                res.update({'journal_id': journal.id})
        return res

    #Column
    invoice_refund_count = fields.Integer(compute='_compute_invoice_refund', string='# of Invoice Refunds',copy=False, default=0,
                                          help='')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.depends('invoice_lines.invoice_id.state','invoice_lines.quantity')
    def _compute_qty_refunded(self):
        '''
        Obtiene la cantidad reembolsada 
        '''
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                inv_type = inv_line.invoice_id.type
                invl_q = inv_line.quantity
                if inv_line.invoice_id.state not in  ['draft','cancel']:
                    if ((inv_type == 'out_invoice' and invl_q < 0.0) or
                        (inv_type == 'out_refund' and invl_q > 0.0)):
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_refunded = qty
 
    @api.depends('order_id.state',  'qty_invoiced',
                 'invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _compute_qty_to_invoice(self):
        '''
        Obtiene la cantidad a reembolsar
        '''
        for line in self:
            line.qty_to_refund = 0.0
            if line.order_id.state not in ('sale', 'done'):
                line.invoice_status = 'no'
                continue
            else:
                if line.product_id.purchase_method == 'receive':
                    qty = (line.product_uom_qty - line.qty_returned) - \
                          (line.qty_invoiced - line.qty_refunded)
                    if qty >= 0.0:
                      line.qty_to_invoice = qty
                    else:
                       line.qty_to_refund = abs(qty)
                else:
                    line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced
                    line.qty_to_refund = 0.0

    @api.depends('order_id.state', 'procurement_ids.move_ids.state')
    def _compute_qty_returned(self):
        '''
        Obtiene la cantidad devuelta
        '''
        for line in self:
             line.qty_returned = 0.0
             qty = 0.0
             for move in line.procurement_ids.mapped('move_ids'):
                 if move.state == 'done' and move.location_dest_id.usage !='customer':
                     qty += move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
             line.qty_returned = qty

    @api.multi
    def _prepare_invoice_line(self, qty):
        '''
        Modifica el valor de cantidad de la factura con la cantidad a devolver.
        '''
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        if self.product_id.purchase_method == 'receive':
            qty = (self.product_uom_qty - self.qty_returned) - (self.qty_invoiced - self.qty_refunded)
            res['quantity'] = qty
        type = self._context.get('type',False)
        if type == 'out_refund':
            account = self.product_id.property_account_customer_refund or self.product_id.categ_id.property_account_customer_refund_categ
            if account:
                res['account_id'] = account.id
            res['quantity'] *= -1.0
        return res
        
    #columns
    qty_to_refund = fields.Float(compute='_compute_qty_to_invoice', string='Qty to Refund', copy=False, default=0.0,
                                 digits=dp.get_precision('Product Unit of Measure'),
                                 help='')
    qty_refunded = fields.Float(compute='_compute_qty_refunded', string='Refunded Qty', copy=False, default=0.0,
                                digits=dp.get_precision('Product Unit of Measure'),
                                help='')
    qty_returned = fields.Float(compute='_compute_qty_returned', string='Returned Qty', copy=False, default=0.0,
                                digits=dp.get_precision('Product Unit of Measure'),
                                help='')
