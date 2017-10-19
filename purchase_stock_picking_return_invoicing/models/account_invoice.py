# -*- coding: utf-8 -*-
# Copyright 2017 Eficent Business and IT Consulting Services
#           <contact@eficent.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    def _prepare_invoice_line_from_po_line(self, line):
        data = super(AccountInvoice,
                     self)._prepare_invoice_line_from_po_line(line)
        if line.product_id.purchase_method == 'receive':
            qty = (line.qty_received - line.qty_returned) - (
                line.qty_invoiced - line.qty_refunded)
            data['quantity'] = qty
        if self.type == 'in_refund':
            invoice_line = self.env['account.invoice.line']
            data['quantity'] *= -1.0
            data['account_id'] = invoice_line.with_context(
                {'journal_id': self.journal_id.id,
                 'type': 'in_invoice'})._default_account(),
            account = invoice_line.get_invoice_line_account(
                'in_invoice', line.product_id,
                self.purchase_id.fiscal_position_id, self.env.user.company_id)
            if account:
                data['account_id'] = account.id
        return data

    @api.multi
    def action_invoice_open(self):
        '''
        Valida que los notas de credito no sean superiores a las cantidades de la orden de compra
        '''
        default_purchase_id = self._context.get('default_purchase_id', False)
        for invoice in self:
            if invoice.type =='in_refund':
                if default_purchase_id:
                    for line_order in self.env['purchase.order'].search([('id','=', default_purchase_id )]).mapped('order_line'):
                        for line_inv in invoice.invoice_line_ids:
                            if line_inv.product_id == line_order.product_id and\
                               line_inv.product_id.purchase_method == 'receive' :
                                if line_inv.quantity > line_order.qty_to_refund or line_inv.quantity <= 0.0:
                                    raise UserError (u'Por favor verifique: '
                                                     u'la cantidad de los productos debe ser mayor a 0.'
                                                     u'la cantidad de los productos no pueden ser superior a la cantidad a retornar de la order de compra %s' % line_order.order_id.name )
        return super(AccountInvoice, self).action_invoice_open()

