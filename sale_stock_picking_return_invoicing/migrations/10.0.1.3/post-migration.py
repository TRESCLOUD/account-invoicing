# -*- coding: utf-8 -*-
# Copyright 2017 Trescloud <http://trescloud.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade
from timeit import default_timer as timer
import logging
_logger = logging.getLogger(__name__)

@openupgrade.logging()
def create_version_field(env):
    '''Creamos un campo para control de version de migracion del modulo:
    1. No usamos python, sino SQL para no contaminar el entorno (asi no aparecen en la exportacion de datos por ejemplo)
    '''
    env.cr.execute(
        """
        ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS sspri_module_version CHARACTER VARYING;
        ;""")
    
@openupgrade.logging()
def create_cron(env):
    '''Crea un cron que invoca al metodo action_compute_sale_line_qty para todas las ventas, e indica que ha sido migrado
    '''
    pass #TODO cargar el cron con un load_xml de openupgrade    
    
@openupgrade.migrate(use_env=True)
def migrate(env, version):
    cr = env.cr
    create_version_field(env)
    create_cron(env)
    
    
    