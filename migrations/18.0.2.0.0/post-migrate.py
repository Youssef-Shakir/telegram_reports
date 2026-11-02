# -*- coding: utf-8 -*-
"""18.0.2.0.0: the Telegram settings are per company. Every company starts with the old global settings."""
from odoo import SUPERUSER_ID, api

PARAMS = {
    'telegram_bot_token': ('telegram_reports.bot_token', str),
    'telegram_default_chat_id': ('telegram_reports.default_chat_id', str),
    'telegram_send_on_pos_close': ('telegram_reports.send_on_pos_close', bool),
    'telegram_pos_close_top_products': ('telegram_reports.pos_close_top_products', bool),
    'telegram_pos_close_top_count': ('telegram_reports.pos_close_top_count', int),
    'telegram_pos_close_send_pdf': ('telegram_reports.pos_close_send_pdf', bool),
    'telegram_send_on_order_cancel': ('telegram_reports.send_on_order_cancel', bool),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter'].sudo()
    values = {}
    for field, (key, kind) in PARAMS.items():
        raw = params.get_param(key)
        if raw in (None, False, ''):
            continue
        if kind is bool:
            values[field] = raw == 'True'
        elif kind is int:
            try:
                values[field] = int(raw)
            except ValueError:
                continue
        else:
            values[field] = raw
    if values:
        env['res.company'].sudo().search([]).write(values)
