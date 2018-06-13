# -*- coding: utf-8 -*-
# Copyright 2017 Eficent Business and IT Consulting Services
#           <contact@eficent.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.depends('order_line.qty_received', 'order_line.move_ids.state')
    def _get_invoiced(self):
        '''
        Actualizamos el estado de la factura utilizando para este fin las 
        lineas de la orden de la compra que almacenan el campo invoice_status.
        '''
        super(PurchaseOrder, self)._get_invoiced()
        for order in self:
            if order.state not in ('purchase', 'done'):
                order.invoice_status = 'no'
                continue
            if any(line.invoice_status == 'to invoice' for line in order.order_line):
                order.invoice_status = 'to invoice'
            elif all(line.invoice_status == 'invoiced' for line in order.order_line):
                order.invoice_status = 'invoiced'
            else:
                order.invoice_status = 'no'

    @api.depends('order_line.invoice_lines.invoice_id.state')
    def _compute_invoice(self):
        '''
        Filtra y cuenta las facturas.
        '''
        super(PurchaseOrder, self)._compute_invoice()
        for order in self:
            invoices = self.env['account.invoice']
            for line in order.order_line:
                invoices |= line.invoice_lines.mapped('invoice_id').filtered(
                    lambda x: x.type == 'in_invoice')
            order.invoice_count = len(invoices)

    @api.multi
    def action_view_invoice_refund(self):
        '''
        This function returns an action that display existing vendor refund
        bills of given purchase order id.
        When only one found, show the vendor bill immediately.
        '''
        action = self.env.ref('account.action_invoice_tree2')
        result = action.read()[0]
        refunds = self.invoice_ids.filtered(lambda x: x.type == 'in_refund')
        # override the context to get rid of the default filtering
        result['context'] = {
            'type': 'in_refund',
            'default_purchase_id': self.id
        }
        if not refunds:
            # Choose a default account journal in the
            # same currency in case a new invoice is created
            journal_domain = [
                ('type', '=', 'purchase'),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
            ]
            default_journal_id = self.env['account.journal'].search(
                journal_domain, limit=1)
            if default_journal_id:
                result['context']['default_journal_id'] = default_journal_id.id
        else:
            # Use the same account journal than a previous invoice
            result['context']['default_journal_id'] = refunds[0].journal_id.id
        # choose the view_mode accordingly
        if len(refunds) != 1:
            result['domain'] = "[('id', 'in', " + str(refunds.ids) + ")]"
        elif len(refunds) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = refunds.id
        return result

    @api.multi
    def action_view_invoice(self):
        result = super(PurchaseOrder, self).action_view_invoice()
        invoices = self.invoice_ids.filtered(lambda x: x.type == 'in_invoice')
        # choose the view_mode accordingly
        if len(invoices) != 1:
            result['domain'] = "[('id', 'in', " + str(invoices.ids) + ")]"
        elif len(invoices) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = invoices.id
        return result
    
    @api.depends('order_line.invoice_lines.invoice_id.state')
    def _compute_invoice_refund(self):
        '''
        Filtra y cuenta las notas de credito.
        '''
        for order in self:
            invoices = self.env['account.invoice']
            for line in order.order_line:
                invoices |= line.invoice_lines.mapped('invoice_id').filtered(
                            lambda x: x.type == 'in_refund')
            order.invoice_refund_count = len(invoices)
    
    @api.multi
    def action_compute_purchase_line_qty(self):
        """
        Permite recalcular los campos qty_delivered, qty_to_invoice, qty_invoiced   
        """
        for purchase in self.with_context(recompute=False):
            for line in purchase.order_line:
                line._compute_qty_received()
                line._compute_qty_to_invoice()
                line._compute_qty_invoiced()
        return True  
    
    #columns
    invoice_refund_count = fields.Integer(
        compute='_compute_invoice_refund',
        string='# of Invoice Refunds',
        copy=False,
        default=0
        )
    

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends('invoice_lines.invoice_id.state','invoice_lines.quantity')
    def _compute_qty_invoiced(self):
        '''
         Obtenemos la cantidad facturada, se sobre escribe por completo el metodo del core.
        el core resta la cantidad facturada menos las notas de credito, funcion que sera remplazada
        manteniendo dos columnas Facturado y  cantidad reembolsada.
        '''
        super(PurchaseOrderLine, self)._compute_qty_invoiced()
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                inv_type = inv_line.invoice_id.type
                invl_q = inv_line.quantity
                if inv_line.invoice_id.state in ['open','paid']:
                    if ((inv_type == 'in_invoice' and invl_q > 0.0) or
                        (inv_type == 'in_refund' and invl_q < 0.0)):
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_invoiced = qty

    @api.depends('invoice_lines.invoice_id.state',
                 'invoice_lines.quantity')
    def _compute_qty_refunded(self):
        '''
        Obtiene la cantidad reembolsada.
        '''
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                inv_type = inv_line.invoice_id.type
                invl_q = inv_line.quantity
                if inv_line.invoice_id.state  in  ['open','paid']:
                    if ((inv_type == 'in_invoice' and invl_q < 0.0) or
                        (inv_type == 'in_refund' and invl_q > 0.0)):
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_refunded = qty

    @api.depends('order_id.state', 'qty_received',
                 'product_qty', 'move_ids.state',
                 'qty_invoiced', 
                 'invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _compute_qty_to_invoice(self):
        '''
         hacemos super al metodo por si en el core existe una restriccion,
        se sobre escribe el metodo agregando una nueva logica para  modificar el campo a facturar y a reembolsar.
        en base a las politicas de facturacion.
        
        para la politica de facturacion por cantidad ordenada se aplica la siguiente formula:
                qty  = (qty_received - qty_returned) - (qty_invoiced - qty_refunded)
                
                Donde:
                qty_received = cantidad recibida
                qty_returned = cantidad devuelta
                qty_invoiced = cantidad en facturas
                qty_refunded = cantidad en notas de credito
                qty = el resultado de aplicar la formula indica 
                      positivo(+) pendendiente de facturar
                      negativo(-) pendiente de emitir una nota de credito 
            
        para la politica de facturacion por cantidad entregada se aplica la siguiente formula:
                qty_to_invoice =  qty_delivered - line.qty_invoiced
                
                Donde:
                product_qty = cantidad despachada
                qty_invoiced = cantidad en facturas
                qty_to_invoice = cantidad a facturar
            
            nota: para la politica de cantidad entregada no es necesario una cantidad a reembolsar
                  por que el calculo se base en la cantidad despachada.
        
        '''
        super(PurchaseOrderLine, self)._compute_qty_to_invoice()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            line.qty_to_refund = 0.0
            line.qty_to_invoice = 0.0
            if line.order_id.state not in ('purchase', 'done'):
                line.invoice_status = 'no'
                continue
            else:
                if line.product_id.purchase_method == 'receive':
                    qty = (line.qty_received - line.qty_returned) - (line.qty_invoiced - line.qty_refunded)
                    if qty >= 0.0:
                        line.qty_to_invoice = qty
                    else:
                        line.qty_to_refund = abs(qty)
                else:
                    qty_to_invoice = (line.product_qty - line.qty_returned) - line.qty_invoiced
                    if qty_to_invoice < 0:
                        line.qty_to_invoice = 0.0
                        line.qty_to_refund = abs(qty_to_invoice)
                    else:
                        line.qty_to_invoice = qty_to_invoice
                        line.qty_to_refund = 0.0
            #actualiza el estado de facturacion.       
            if line.product_id.purchase_method == 'receive' and not line.move_ids.filtered(lambda x: x.state == 'done'):
                line.invoice_status = 'to invoice'
                # We would like to put 'no', but that would break standard
                # odoo tests.
                continue
            if abs(float_compare(line.qty_to_invoice, 0.0, precision_digits=precision)) == 1:
                line.invoice_status = 'to invoice'
            elif abs(float_compare(line.qty_to_refund, 0.0, precision_digits=precision)) == 1:
                line.invoice_status = 'to invoice'
            elif float_compare(line.qty_to_invoice, 0.0,precision_digits=precision) == 0 and \
                 float_compare(line.qty_to_refund, 0.0, precision_digits=precision) == 0:
                line.invoice_status = 'invoiced'
            else:
                line.invoice_status = 'no'

    @api.depends('order_id.state', 'move_ids.state')
    def _compute_qty_returned(self):
        '''
         Obtiene la cantidad devuelta en base al movimientos de inventario.
        '''
        for line in self:
            line.qty_returned = 0.0
            qty = 0.0
            for move in line.move_ids:
                if move.state == 'done' and move.location_id.usage != 'supplier':
                    if move.product_uom != line.product_uom:
                        qty = move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
                    else:
                        qty = move.product_uom_qty
            line.qty_returned = qty

    @api.depends('order_id.state', 'move_ids.state', 'move_ids', 'qty_returned')
    def _compute_qty_received(self):
        '''
        Mantiene el valor recibido restando la cantidad devuelta.
        '''
        super(PurchaseOrderLine, self)._compute_qty_received()
        for line in self:
            for move in line.move_ids:
                if move.state == 'done' and move.location_id.usage != 'supplier':
                    if move.product_uom != line.product_uom:
                        qty = move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
                    else:
                        qty = move.product_uom_qty
                    line.qty_received -= qty
    
    #columns
    qty_to_refund = fields.Float(
        compute="_compute_qty_to_invoice",
        string='Qty to Refund',
        copy=False,
        default=0.0,
        help='Cantidad pendiente a reembolsar, Se calcula cuando la siguente fórmula retorna un valor negativo:'
             '(cantidad recibida - cantidad devuelta) - (cantidad facturada - notas de crédito emitidas)'
             'En base a Cant. a reembolsar se genera la nota de crédito.'
        )
    qty_refunded = fields.Float(
        compute="_compute_qty_refunded",
        string='Refunded Qty',
        copy=False,
        default=0.0,
        help='Se calcula con la suma de las facturas con cantidad negativas.'
        )
    qty_returned = fields.Float(
        compute="_compute_qty_returned",
        string='Returned Qty',
        copy=False,
        default=0.0,
        help='Cantidad devuelta, se obtiene en base a los movimientos de devolución de mercaderia '
             'en estado realizado.'
        )
    invoice_status = fields.Selection([
        ('no', 'Not purchased'),
        ('to invoice', 'Waiting Invoices'),
        ('invoiced', 'Invoice Received'),
        ],
        string='Invoice Status',
        compute='_compute_qty_to_invoice',
        readonly=True,
        copy=False,
        default='no'
        )
