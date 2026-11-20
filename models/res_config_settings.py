# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Per company (the company chosen at the top of Settings)
    telegram_enabled = fields.Boolean(related='company_id.telegram_enabled', readonly=False)
    telegram_bot_token = fields.Char(related='company_id.telegram_bot_token', readonly=False,
                                     help='Telegram Bot Token from @BotFather')
    telegram_default_chat_id = fields.Char(related='company_id.telegram_default_chat_id', readonly=False,
                                           help='Default Telegram Chat ID or Group ID')
    telegram_chat_pos = fields.Char(related='company_id.telegram_chat_pos', readonly=False)
    telegram_chat_summary = fields.Char(related='company_id.telegram_chat_summary', readonly=False)
    telegram_chat_reports = fields.Char(related='company_id.telegram_chat_reports', readonly=False)
    telegram_chat_order_now = fields.Char(related='company_id.telegram_chat_order_now', readonly=False)
    telegram_send_on_pos_close = fields.Boolean(related='company_id.telegram_send_on_pos_close', readonly=False,
                                                help='Automatically send sales summary when POS session is closed')
    telegram_pos_close_top_products = fields.Boolean(related='company_id.telegram_pos_close_top_products',
                                                     readonly=False)
    telegram_pos_close_top_count = fields.Integer(related='company_id.telegram_pos_close_top_count', readonly=False)
    telegram_pos_close_send_pdf = fields.Boolean(related='company_id.telegram_pos_close_send_pdf', readonly=False)
    telegram_send_on_order_cancel = fields.Boolean(related='company_id.telegram_send_on_order_cancel',
                                                   readonly=False)
    telegram_order_now = fields.Boolean(related='company_id.telegram_order_now', readonly=False)
    telegram_order_now_time = fields.Float(related='company_id.telegram_order_now_time', readonly=False)
    telegram_order_now_available = fields.Boolean(compute='_compute_telegram_order_now_available')
    # Computed
    telegram_report_count = fields.Integer(
        string='Scheduled Reports',
        compute='_compute_telegram_report_count'
    )

    telegram_summary_count = fields.Integer(
        string='Daily Summaries',
        compute='_compute_telegram_summary_count'
    )

    def _compute_telegram_report_count(self):
        """Count active scheduled reports."""
        for record in self:
            record.telegram_report_count = self.env['telegram.report.schedule'].search_count([
                ('active', '=', True), ('company_id', '=', record.company_id.id)
            ])

    def _compute_telegram_summary_count(self):
        """Count active daily summaries."""
        for record in self:
            record.telegram_summary_count = self.env['telegram.daily.summary'].search_count([
                ('active', '=', True), ('company_id', '=', record.company_id.id)
            ])

    def _compute_telegram_order_now_available(self):
        for record in self:
            record.telegram_order_now_available = self.env['telegram.order.now']._available()

    def action_telegram_send_order_now(self):
        """Send today's Order Now list now (saved settings)."""
        self.ensure_one()
        sent = self.env['telegram.order.now']._send(self.company_id, force=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Order Now'), 'type': 'success' if sent else 'info',
            'message': _('Sent to Telegram.') if sent else _('Nothing to order today: nothing was sent.')}}

    def action_test_telegram_connection(self):
        """Test the bot token and the main group (what is typed, even before saving)."""
        self.ensure_one()

        telegram = self.env['telegram.service'].with_company(self.company_id)
        result = telegram.test_connection(
            token=self.telegram_bot_token,
            chat_id=self.telegram_default_chat_id
        )

        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': result['message'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(result['message'])

    def action_open_telegram_schedules(self):
        """Open scheduled reports configuration."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Telegram Report Schedules'),
            'res_model': 'telegram.report.schedule',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_telegram_summaries(self):
        """Open daily summaries configuration."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Telegram Daily Summaries'),
            'res_model': 'telegram.daily.summary',
            'view_mode': 'list,form',
            'target': 'current',
        }
