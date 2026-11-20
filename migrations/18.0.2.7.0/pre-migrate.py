# -*- coding: utf-8 -*-
"""donialink_app_telegram was folded into telegram_reports (group alerts) and expense_cash_control_telegram (owner
cash box). Its group alert records (kinds, the "Send to Telegram" setting and its field) get the same XML id in
this module, so they stay when donialink_app_telegram is uninstalled: Odoo keeps a record that another module
still names."""
import logging

_logger = logging.getLogger(__name__)

OLD_MODULE = 'donialink_app_telegram'
NAMES = (
    'kind_pos_session', 'kind_pos_order_alert', 'kind_daily_summary', 'kind_finance_summary',
    'kind_scheduled_report', 'kind_order_now', 'res_config_settings_view_form_dl_app_telegram',
    'field_res_company__dl_telegram_enabled', 'field_res_config_settings__dl_telegram_enabled',
)


def migrate(cr, version):
    cr.execute("""
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_uid, create_date, write_uid,
                                   write_date)
        SELECT 'telegram_reports', old.name, old.model, old.res_id, old.noupdate, old.create_uid, old.create_date,
               old.write_uid, now() AT TIME ZONE 'UTC'
          FROM ir_model_data old
         WHERE old.module = %s AND old.name IN %s
           AND NOT EXISTS (SELECT 1 FROM ir_model_data new WHERE new.module = 'telegram_reports' AND new.name = old.name)
    """, [OLD_MODULE, NAMES])
    _logger.info('telegram_reports: %s records taken over from %s', cr.rowcount, OLD_MODULE)
