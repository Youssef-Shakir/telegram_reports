# -*- coding: utf-8 -*-
"""18.0.2.2.0: companies left without a bot token / chat ID by the per-company switch get the old global ones back."""
from odoo import SUPERUSER_ID, api

PARAMS = {
    'telegram_bot_token': 'telegram_reports.bot_token',
    'telegram_default_chat_id': 'telegram_reports.default_chat_id',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter'].sudo()
    companies = env['res.company'].sudo().search([])
    for field, key in PARAMS.items():
        value = params.get_param(key)
        if value:
            companies.filtered(lambda c: not c[field]).write({field: value})
