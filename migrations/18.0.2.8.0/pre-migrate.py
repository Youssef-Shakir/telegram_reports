# -*- coding: utf-8 -*-
"""Telegram through the DoniaLink Platform is gone: Telegram is now optional, through the company's own bot
("Also send to Telegram"). It stays on for the companies that sent through their own bot (token and group set,
not switched off); the ones that went through the platform get the DoniaLink App only. The old fields
(telegram_delivery, dl_telegram_enabled) are removed by the update."""
import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               [table, column])
    return bool(cr.fetchone())


def migrate(cr, version):
    # the "Send to Telegram" settings view (from donialink_app_telegram) names a field that is gone: it must go
    # before the settings view it extends is checked again
    cr.execute("""
        DELETE FROM ir_ui_view WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'telegram_reports' AND name = 'res_config_settings_view_form_dl_app_telegram')
    """)
    cr.execute("""DELETE FROM ir_model_data
                   WHERE module = 'telegram_reports' AND name = 'res_config_settings_view_form_dl_app_telegram'""")
    if _column_exists(cr, 'res_company', 'telegram_enabled'):
        return
    cr.execute("ALTER TABLE res_company ADD COLUMN telegram_enabled boolean")
    own_bot = "COALESCE(telegram_delivery, 'bot') = 'bot'" if _column_exists(cr, 'res_company', 'telegram_delivery') \
        else 'TRUE'
    not_off = 'COALESCE(dl_telegram_enabled, TRUE)' if _column_exists(cr, 'res_company', 'dl_telegram_enabled') \
        else 'TRUE'
    cr.execute(f"""
        UPDATE res_company
           SET telegram_enabled = ({own_bot} AND COALESCE(telegram_bot_token, '') != ''
                                   AND COALESCE(telegram_default_chat_id, '') != '' AND {not_off})
    """)
    cr.execute("SELECT count(*) FROM res_company WHERE telegram_enabled")
    _logger.info('telegram_reports: Telegram kept on for %s company(ies) with their own bot', cr.fetchone()[0])
