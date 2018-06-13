# -*- coding: utf-8 -*-
# Copyright 2017 Eficent Business and IT Consulting Services
# Copyright 2018 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    #columns
    invoice_refund_count = fields.Integer(
        compute="_compute_invoice_refund_count",
        string='# of Invoice Refunds',
        copy=False,
        default=0
        )

    @api.depends('state',
                 'order_line.qty_invoiced',
                 'order_line.qty_received',
                 'order_line.product_qty',
                 'order_line.invoice_status', #TODO: Este campo es funcional!
                 )
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
    def _compute_invoice_refund_count(self):
        '''
        Filtra y cuenta las notas de credito.
        '''
        for order in self:
            invoices = order.mapped(
                'order_line.invoice_lines.invoice_id'
            ).filtered(lambda x: x.type == 'in_refund')
            order.invoice_refund_count = len(invoices)

    @api.depends('invoice_refund_count')
    def _compute_invoice(self):
        """Change computation for excluding refund invoices.
        Make this compatible with other extensions, only subtracting refunds
        from the number obtained in super.
        """
        super(PurchaseOrder, self)._compute_invoice()
        for order in self:
            order.invoice_count -= order.invoice_refund_count

    @api.multi
    def action_view_invoice_refund(self):
        """This function returns an action that display existing vendor refund
        bills of given purchase order id.
        When only one found, show the vendor bill immediately.
        """
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
            result['domain'] = [('id', 'in', refunds.ids)]
        elif len(refunds) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = refunds.id
        return result

    @api.multi
    def action_view_invoice(self):
        """Change super action for displaying only normal invoices."""
        result = super(PurchaseOrder, self).action_view_invoice()
        invoices = self.invoice_ids.filtered(
            lambda x: x.type == 'in_invoice'
        )
        # choose the view_mode accordingly
        if len(invoices) != 1:
            result['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = invoices.id
        return result

    
    @api.multi
    def action_compute_purchase_line_qty(self):
        """
        Permite recalcular los campos qty_delivered, qty_to_invoice, qty_invoiced   
        """
        for purchase in self.with_context(recompute=False):
            for line in purchase.order_line:
                line._compute_qty_received()
                line._compute_qty_invoiced()
                line._compute_qty_to_invoice()
            purchase._get_invoiced() #actualizamos el estado de facturacion de la orden
        return True    

    @api.model
    def cron_compute_purchase_line_qty(self):
        '''
        Este metodo invoca los procesos de forma automatica para recalcular en las lineas de compra los campos
        qty_received, qty_invoice, qty_to_invoice que aun no hayan sido reprocesadas (campo reprocess_lines = False)
        '''
        time_start = timer()
        purchase_ids= self.search([('reprocess_lines', '=', False)], order='id desc')
        # No hay compras que reprocesar, deshabilito el cron
        if not purchase_ids:
            xml_data_cron = self.env['ir.model.data'].search([('name', '=', 'process_pending_action_compute_purchase_line_qty'), ('module', '=', 'purchase_stock_picking_return_invoicing')])
            if xml_data_cron:
                self.env['ir.cron'].browse(xml_data_cron[0].res_id).active = False
                self.env.cr.commit()
            return True
        count = 0
        total_purchase = len(purchase_ids)
        for purchase in purchase_ids:
            try:
                _logger.info("1. Inicia procesamiento de las lineas de la compra de ID: %s. ", purchase.id)
                start_document = timer()
                #usamos recompute=False para evitar disparar campos funcionales
                purchase.with_context(recompute=False).action_compute_purchase_line_qty()
                end_lines = timer()
                delta_lines = end_lines - start_document
                _logger.info("2. Procesadas %s lineas de la compra ID: %s. Tiempo (seg): %s.",len(purchase.order_line), purchase.id, "%.3f" % delta_lines)
                time.sleep(0.05) #nos detenemos 50 ms para no bloquear la bdd en produccion
                count +=1
            except Exception: #si hay error obviamos su computo y seguimos
                _logger.error("La compra de ID: %s no pudo ser computada.",str(purchase.id))
                self._cr.rollback() #reversamos al ultimo commit, es decir se van todos los calculos de este documento
                self.env.cr.commit()
            else: #si todo funciona bien continuamos
                purchase.reprocess_lines = True
                self.env.cr.commit()
                end_document = timer()
                delta_document = end_document - start_document
                _logger.info("3. Procesada compra %s de %s. ID: %s. Tiempo (seg): %s.",count, total_purchase, purchase.id, "%.3f" % delta_document)
                time.sleep(0.05) #nos detenemos 50 ms para no bloquear la bdd en produccion
        time_end = timer()

    #Columns
    reprocess_lines = fields.Boolean(
        string='This purchase order was recomputed?',
        default=False, 
        help="Show if this purchase order was recomputed or not" 
        )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

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
            inv_lines = line.invoice_lines.filtered(lambda x: (
                (x.invoice_id.type == 'in_invoice' and x.quantity < 0.0) or
                (x.invoice_id.type == 'in_refund' and x.quantity > 0.0)
            ))
            line.qty_refunded = sum(inv_lines.mapped(lambda x: (
                x.uom_id._compute_quantity(x.quantity, line.product_uom)
            )))

    @api.depends('order_id.state', 'qty_received',
                 'product_qty', 'move_ids.state',
                 'qty_invoiced', 
                 'invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _compute_qty_to_invoice(self):
        '''
        Hacemos super al metodo por si en el modulo heredado "purchase_open_qty" existe una restriccion,
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
            qty_to_refund = 0.0
            qty_to_invoice = 0.0
            if line.order_id.state in ('purchase', 'done'):
                if line.product_id.purchase_method == 'receive':
                    qty = (line.qty_received - line.qty_returned) - (line.qty_invoiced - line.qty_refunded)
                    if qty >= 0.0:
                        qty_to_invoice = qty
                    else:
                        qty_to_refund = abs(qty)
                else:
                    qty_to_invoice = (line.product_qty - line.qty_returned) - line.qty_invoiced
                    if qty_to_invoice < 0:
                        qty_to_invoice = 0.0
                        qty_to_refund = abs(qty_to_invoice)
                    else:
                        qty_to_invoice = qty_to_invoice
                        qty_to_refund = 0.0
            line.qty_to_refund = qty_to_refund
            line.qty_to_invoice = qty_to_invoice
        
    @api.depends('qty_to_invoice',
                 'qty_to_refund',
                 )
    def _get_invoiced(self):
        '''Computa el estado de facturacion de cada linea, util para computar el estado de facturacion de la cabecera
        '''
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            invoice_status = 'no'
            if line.order_id.state in ('purchase', 'done'):
                if abs(float_compare(line.qty_to_invoice, 0.0, precision_digits=precision)) == 1 or \
                   abs(float_compare(line.qty_to_refund, 0.0, precision_digits=precision)) == 1:
                    invoice_status = 'to invoice'
                elif float_compare(line.qty_to_invoice, 0.0,precision_digits=precision) == 0 and \
                     float_compare(line.qty_to_refund, 0.0, precision_digits=precision) == 0:
                    invoice_status = 'invoiced'
                else:
                    invoice_status = 'no'
            line.invoice_status = invoice_status

    @api.depends(
        'move_ids.state',
        'move_ids.returned_move_ids.state',
    )
    def _compute_qty_returned(self):
        '''
         Obtiene la cantidad devuelta en base al movimientos de inventario.
        '''
        for line in self:
            qty = 0.0
            moves = line.mapped('move_ids.returned_move_ids')
            for move in moves.filtered(lambda x: x.state == 'done'):
                if move.location_id.usage != 'supplier':
                    qty += move.product_uom._compute_quantity(
                        move.product_uom_qty, line.product_uom,
                    )
            line.qty_returned = qty

    @api.depends('qty_returned')
    def _compute_qty_received(self):
        """Substract returned quantity from received one, as super sums
        only direct moves, and we want to reflect here the actual received qty.
        Odoo v11 also does this.
        """
        '''
        Mantiene el valor recibido restando la cantidad devuelta.
        '''
        super(PurchaseOrderLine, self)._compute_qty_received()
        for line in self:
            line.qty_received -= line.qty_returned

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
        compute='_get_invoiced',
        readonly=True,
        copy=False,
        default='no',
        help='Estado de facturacion, se replica a la cabecera de la orden de compra'
        )

