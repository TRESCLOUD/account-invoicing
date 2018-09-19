# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError
import odoo.addons.decimal_precision as dp
from odoo.tools import float_is_zero
from timeit import default_timer as timer
import time
import logging
_logger = logging.getLogger(__name__)


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
        Actualiza el campo estado factura.
        '''
        super(SaleOrder, self)._get_invoiced()
        for order in self:
            invoice_ids = order.order_line.mapped('invoice_lines').mapped('invoice_id').filtered(lambda r: r.type in ['out_invoice'])
            order.update({
                'invoice_count': len(set(invoice_ids.ids)),
                'invoice_ids': invoice_ids.ids
            })
            if order.force_state != 'automatic':
                 order.update({
                'invoice_status': order.force_state 
            })
        
    @api.multi
    def action_view_invoice_refund(self):
        '''
        Visualiza las notas de credito asociadas a una factura
        '''
        #computamos el id de la factura sobre la cual emito la NC
        invoice_ids = self.invoice_ids.filtered(lambda x: x.type == 'out_invoice' and x.state not in ('cancel','draft')).mapped('id')
        ctx = self._context.copy()
        ctx.update({'type':'out_refund'})
        ctx.update({'default_invoice_rectification_id': invoice_ids[0] if invoice_ids else []})
        #consruyo el formulario o tree de respuesta
        action = self.env.ref('account.action_invoice_tree1')
        result = action.read()[0]
        result['domain']= [('type', '=', ('out_refund')),('partner_id','=', self.partner_id.id)]
        result['context'] = {
            'type': 'out_refund',
            'default_sale_id': self.id
        }
        refunds = self.invoice_ids.filtered(lambda x: x.type == 'out_refund')
        if len(refunds) == 1:
            result['views'] = [(self.with_context(ctx).env.ref('account.invoice_form').id, 'form')]
            result['res_id'] = refunds.id
        else:
            result['domain'] = [('id', 'in', refunds.ids)]
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
        tiene la logica de crear las lineas de la factura si la cantidad a reembolsar es diferente de cero.
        Nota: Metodo deprecado temporalmente para crear NCs por cada devolucion en ventas (MA-1031)
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
        se actualiza la lineas de la factura para setear campos por defecto.
        '''
        res = super(SaleOrder, self)._prepare_invoice()
        if self.env.context.get('type',False) == 'out_refund':
            invoice = self.env['account.invoice'].browse(self.env.context.get('default_invoice_rectification_id',False))
            res.update({'type':'out_refund',
                        'default_invoice_rectification_id': invoice.id,
                        'user_id': invoice.user_id.id,
                        'team_id': invoice.team_id.id,
                        'name': u'Devolución de mercadería',
                        'payment_method_id': invoice.payment_method_id.id
            })
            #diario
            journal_domain = [('type', '=', 'sale'),('company_id', '=', self.company_id.id)]
            journal = self.env['account.journal'].search(journal_domain, limit=1)
            if journal:
                res.update({'journal_id': journal.id})
        return res
    
    @api.multi
    def action_compute_sale_line_qty(self):
        """
        Permite recalcular los campos qty_delivered, qty_to_invoice, qty_invoiced   
        """
        for sale in self:
            for line in sale.order_line:
                line.qty_delivered = line._get_delivered_qty()
                line._get_to_invoice_qty()
                line._get_invoice_qty()
        return True    

    @api.model
    def cron_compute_sale_line_qty(self):
        '''
        Este metodo invoca los procesos de forma automatica para recalcular en las lineas de venta los campos
        qty_delivered, to_invoice_qty, invoice_qty que aun no hayan sido reprocesadas (campo reprocess_lines = False)
        '''
        time_start = timer()
        # reprocesamos todas las lineas de todas las ventas que aun
        sale_ids = self.search([('reprocess_lines', '=', False)], order='id desc')
        # No hay ventas que reprocesar, deshabilito el cron
        if not sale_ids:
            xml_data_cron = self.env['ir.model.data'].search([('name', '=', 'process_pending_action_compute_sale_line_qty'), ('module', '=', 'sale_stock_picking_return_invoicing')])
            if xml_data_cron:
                self.env['ir.cron'].browse(xml_data_cron[0].res_id).active = False
                self.env.cr.commit()
            return True
        count = 0
        total_sale = len(sale_ids)
        for sale in sale_ids:
            try:
                _logger.info("1. Inicia procesamiento de las lineas de la venta de ID: %s. ", sale.id)
                start_document = timer()
                #usamos recompute=False para evitar disparar campos funcionales
                sale.with_context(recompute=False).action_compute_sale_line_qty()
                end_lines = timer()
                delta_lines = end_lines - start_document
                _logger.info("2. Procesadas %s lineas de la venta ID: %s. Tiempo (seg): %s.",len(sale.order_line), sale.id, "%.3f" % delta_lines)
                time.sleep(0.05) #nos detenemos 50 ms para no bloquear la bdd en produccion
                count +=1
            except Exception: #si hay error obviamos su computo y seguimos
                _logger.error("La venta ID: %s no pudo ser computada.",str(sale.id))
                self._cr.rollback() #reversamos al ultimo commit, es decir se van todos los calculos de este documento
                self.env.cr.commit()
            else: #si todo funciona bien continuamos
                sale.reprocess_lines = True
                self.env.cr.commit()
                end_document = timer()
                delta_document = end_document - start_document
                _logger.info("3. Procesada venta %s de %s. ID: %s. Tiempo (seg): %s.",count, total_sale, sale.id, "%.3f" % delta_document)
                time.sleep(0.05) #nos detenemos 50 ms para no bloquear la bdd en produccion
        #self._cr.close()
        time_end = timer()
    
    @api.onchange('force_state','invoice_status')
    def onchange_force_state(self):
        '''
        Modificamos el estado del invoice_status tanto en las cabecera
        como en las lineas de la factura
        '''
        if self.force_state != 'automatic':
            self.invoice_status = self.force_state
            for line in self.mapped('order_line'):
                line.invoice_status = self.force_state
  
    
    def _get_selection_invoice_status(self):
        '''
        Asignamos las opciones del seleccion en base 
        al campo invoice_status, ademas de , agregar el estado automatico.
        '''
        res = [('automatic', 'Automático')]
        #TODO: solo deberian tener la opción de automatico y facturado.
        #puede causar muchos errores en el futuro
        res += self.env['sale.order'].fields_get(allfields=['invoice_status'])['invoice_status']['selection']
        return res
        
    
    _selection_invoice_status = lambda self: self._get_selection_invoice_status()

    #Columns
    reprocess_lines = fields.Boolean(
        string='This order lines was recomputed?',
        default=False, 
        help="Show if this order lines was recomputed or not" 
        )
    invoice_refund_count = fields.Integer(
        compute='_compute_invoice_refund', 
        string='# of Invoice Refunds',
        copy=False, 
        default=0,
        help='',
        )
    force_state = fields.Selection(
        string='To force state',
        selection=_selection_invoice_status,
        track_visibility='onchange',
        copy=False,
        default='automatic',
        help='Permite actualizar el campo Estado Factura.',
    )



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'  

    @api.multi
    def _prepare_invoice_line(self, qty):
        '''al crear la linea de nota de credito enlazamos las lineas de factura con los stock.move'''
        vals = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        if self._context.get('refund_move_ids',False):
            #cuando se emite nota de credito por devolucion en ventas
            move_ids = self._context.get('refund_move_ids',False)
            vals['refund_stock_move_ids'] = [(6, 0, move_ids)]
        return vals

    @api.multi
    def _get_delivered_qty(self):
        '''
        Metodo modifica la cantidad entregada en el pedido de ventas,
        manteniendo el valor entregado una vez registrada la devolucion.
        '''
        qty = super(SaleOrderLine, self)._get_delivered_qty()
        for move in self.procurement_ids.mapped('move_ids').filtered(lambda r: r.state == 'done' and not r.scrapped):
            if move.location_dest_id.usage != "customer" and move.to_refund_so:
                #revertimos la operacion original para mantener la cantidad entregada.
                qty += move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom)
        return qty
    
    @api.depends('invoice_lines.invoice_id.state','invoice_lines.quantity')
    def _compute_qty_refunded(self):
        '''
        Obtiene la cantidad reembolsada.
        '''
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                inv_type = inv_line.invoice_id.type
                invl_q = inv_line.quantity
                #la siguiente linea puede causar la creacion de n notas de credito en estado borrador
                #para crear las notas de credito utiliza el campo qty_to_refunded 
                #que se basa en qty_refunded campo utilizado para el calculo
                if inv_line.invoice_id.state in ('open','paid'):
                    if ((inv_type == 'out_invoice' and invl_q < 0.0) or
                        (inv_type == 'out_refund' and invl_q > 0.0)):
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_refunded = qty
    
    @api.depends('invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _get_invoice_qty(self):
        '''
        Obtenemos la cantidad facturada, se sobre escribe por completo el metodo del core.
        el core resta la cantidad facturada menos las notas de credito, funcion que sera remplazada
        manteniendo dos columnas Facturado y  cantidad reembolsada.
        '''
        super(SaleOrderLine, self)._get_invoice_qty()
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                invl_q = inv_line.quantity
                if inv_line.invoice_id.state in ('open','paid'):
                    if ((inv_line.invoice_id.type == 'out_invoice' and invl_q > 0.0) or
                        (inv_line.invoice_id.type == 'out_refund' and invl_q < 0.0)):
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_invoiced = qty
 
    @api.depends('qty_invoiced', 'qty_delivered', 'product_uom_qty', 'order_id.state')
    def _get_to_invoice_qty(self):
        '''
        hacemos super al metodo por si en el core existe una restriccion,
        se sobre escribe el metodo agregando una nueva logica para  modificar el campo a facturar y a reembolsar.
        en base a las politicas de facturacion.
        
        para la politica de facturacion por cantidad ordenada se aplica la siguiente formula:
                qty  = (product_uom_qty - qty_returned) - (qty_invoiced - qty_refunded)
                
                Donde:
                product_uom_qty = cantidad ordenada
                qty_returned = cantidad devuelta
                qty_invoiced = cantidad en facturas
                qty_refunded = cantidad en notas de credito
                qty = el resultado de aplicar la formula indica 
                      positivo(+) pendendiente de facturar
                      negativo(-) pendiente de realizar una nota de credito 
            
        para la politica de facturacion por cantidad entregada se aplica la siguiente formula:
                qty_to_invoice =  qty_delivered - line.qty_invoiced
                
                Donde:
                qty_delivered = cantidad despachada
                qty_invoiced = cantidad en facturas
                qty_to_invoice = cantidad a facturar
            
            nota: para la politica de cantidad entregada no es necesario una cantidad a reembolsar
                  por que el calculo se base en la cantidad despachada.
        
        '''
        super(SaleOrderLine, self)._get_to_invoice_qty()
        for line in self:
            qty_to_refund = 0.0
            qty_to_invoice = 0.0
            if line.order_id.state in ['sale', 'done']:
                if line.product_id.invoice_policy == 'order':
                    qty_ordered_real = line.product_uom_qty
                    qty_delivered_real = line.qty_delivered - line.qty_returned
                    qty_invoiced_real = line.qty_invoiced - line.qty_refunded
                    qty_to_invoice = max(max(qty_ordered_real, qty_delivered_real) - qty_invoiced_real, 0.0)
                    if qty_delivered_real < qty_invoiced_real:
                        #la nota de credito depende de lo ya facturado, no de lo pedido
                        qty_to_refund = qty_invoiced_real - qty_delivered_real
                elif line.product_id.invoice_policy == 'delivery':
                    qty_to_invoice = line.qty_delivered - line.qty_invoiced
                    if qty_to_invoice < 0:
                        qty_to_invoice = 0.0
                        qty_to_refund = abs(qty_to_invoice)
                    else:
                        qty_to_invoice = qty_to_invoice
                        qty_to_refund = 0.0
            line.qty_to_refund = qty_to_refund
            line.qty_to_invoice = qty_to_invoice
    
    @api.depends('state', 'product_uom_qty', 'qty_delivered', 'qty_to_invoice', 'qty_invoiced')
    def _compute_invoice_status(self):
        '''
        By pass para forzar el estado de las lineas.
        '''
        if 'automatic' not in self.mapped('order_id.force_state'):
            for line in self:
                line.invoice_status = line.order_id.force_state
        else:
            super(SaleOrderLine, self)._compute_invoice_status()
    
    @api.depends('order_id.state', 'procurement_ids.move_ids.state')
    def _compute_qty_returned(self):
        '''
        Obtiene la cantidad devuelta en base al movimientos de los grupos de abastecimientos.
        '''
        for line in self:
             line.qty_returned = 0.0
             qty = 0.0
             for move in line.procurement_ids.mapped('move_ids'):
                 if move.state == 'done' and move.location_dest_id.usage !='customer':
                     qty += move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
             line.qty_returned = qty
    
    @api.model
    def _get_qty_delivered(self):
        '''Agrega el concepto de cantidades devueltas'''
        qty_delivered = super(SaleOrderLine, self)._get_qty_delivered()
        qty_delivered -= self.qty_returned
        return qty_delivered
    
    @api.model
    def _get_qty_invoiced(self):
        '''Agrega el concepto de qtys en notas de credito'''
        qty_invoiced = super(SaleOrderLine, self)._get_qty_invoiced()
        qty_invoiced -= self.qty_refunded
        return qty_invoiced
    
    def _get_protected_fields(self):
        '''
        Bypass a la validacion al editar campos bloqueados solo en el caso
        que se setee el campo forzar estado a "nada que facturara".
        
        El metodo fue agregado en  las nuevas actualizaciones del 
        core 2018-01-09.
        '''
        res = super(SaleOrderLine, self)._get_protected_fields()
        #res = listado de campos a bloquear
        if self.order_id and self.order_id._fields.get('force_state', False):
            if self.order_id.force_state == 'no':
                res = []
        return res
    
    #columns
    qty_delivered = fields.Float(
        help='Cantidad total entregada al cliente, se obtiene en base a la suma de la cantidad '
             'de las salidas de bodega en estado realizado.'
        )
    qty_to_invoice = fields.Float(
        help='Cantidad pendiente de facturar, se calcula en base a la siguente fórmula:'
             '(cantidad entregada - cantidad devuelta) - (cantidad facturada - notas de crédito emitidas)'
        )
    qty_to_refund = fields.Float(
        compute='_get_to_invoice_qty',
        string='Qty to Refund',
        copy=False,
        default=0.0,
        digits=dp.get_precision('Product Unit of Measure'),
        help='Cantidad pendiente a reembolsar, Se calcula cuando la siguente fórmula retorna un valor negativo:'
             '(cantidad entregada - cantidad devuelta) - (cantidad facturada - notas de crédito emitidas)'
             'En base a Cant. a reembolsar se genera la nota de crédito.'
        )
    qty_refunded = fields.Float(
        compute='_compute_qty_refunded',
        string='Refunded Qty',
        copy=False,
        default=0.0,
        digits=dp.get_precision('Product Unit of Measure'),
        help='Se calcula con la suma de las facturas con cantidad negativas.'
        )
    qty_returned = fields.Float(
        compute='_compute_qty_returned',
        string='Returned Qty',
        copy=False,
        default=0.0,
        digits=dp.get_precision('Product Unit of Measure'),
        help='Cantidad devuelta desde bodega, se obtiene en base a los movimientos de devolución de mercaderia '
             'en estado realizado.'
        )
    
    