# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The new "Printer offline" app kind: the same recipients as the cancelled orders (once)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['donialink.app.kind']._dl_printer_kind_recipients()
