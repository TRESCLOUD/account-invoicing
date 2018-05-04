# -*- coding: utf-8 -*-
# Copyright 2017 Trescloud <http://trescloud.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade
from timeit import default_timer as timer
import logging
_logger = logging.getLogger(__name__)

@openupgrade.logging()
def update_sale_line_fields(env):
        '''
        Este metodo invoca los procesos de forma automatica para recalcular en las lineas de venta los campos
        qty_delivered, to_invoice_qty, invoice_qty
        '''
        time_start = timer()
        # reprocesamos todas las lineas de todas las ventas
        sale_ids = env['sale.order'].search([], order='id desc')
        count = 0
        total_sale = len(sale_ids)
        for sale in sale_ids:
            #try:
            _logger.info("1. Inicia procesamiento venta ID: %s. ", sale.id)
            start_document = timer()
            #usamos recompute=False para evitar disparar campos funcionales
            sale.with_context(recompute=False).action_compute_sale_line_qty()
            end_lines = timer()
            delta_lines = end_lines - start_document
            _logger.info("2. Procesadas %s lineas de la venta ID: %s. Tiempo (seg): %s.",len(sale.order_line), sale.id, "%.3f" % delta_lines)
            count +=1
        time_end = timer()
        time_delta = time_end - time_start
        return_message = "Se procesaron " + str(count) + \
                         " ventas en " + "%.3f" % time_delta + \
                         " segundos"
        _logger.info(return_message)


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    cr = env.cr
    update_sale_line_fields(env)