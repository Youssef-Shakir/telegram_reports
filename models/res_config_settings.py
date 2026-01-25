# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Bot Configuration
    telegram_bot_token = fields.Char(
        string='Bot Token',
        config_parameter='telegram_reports.bot_token',
        help='Telegram Bot Token from @BotFather'
    )

    telegram_default_chat_id = fields.Char(
        string='Default Chat ID',
        config_parameter='telegram_reports.default_chat_id',
        help='Default Telegram Chat ID or Group ID'
    )

    # POS Session Close Settings
    telegram_send_on_pos_close = fields.Boolean(
        string='Send on POS Session Close',
        config_parameter='telegram_reports.send_on_pos_close',
        help='Automatically send sales summary when POS session is closed'
    )

    telegram_pos_close_top_products = fields.Boolean(
        string='Include Top Products',
        config_parameter='telegram_reports.pos_close_top_products',
        default=True,
        help='Include top selling products in session close message'
    )

    telegram_pos_close_top_count = fields.Integer(
        string='Top Products Count',
        config_parameter='telegram_reports.pos_close_top_count',
        default=5,
        help='Number of top products to show'
    )

    telegram_pos_close_send_pdf = fields.Boolean(
        string='Send PDF Report',
        config_parameter='telegram_reports.pos_close_send_pdf',
        default=False,
        help='Also send PDF report with order details (if available)'
    )

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
                ('active', '=', True)
            ])

    def _compute_telegram_summary_count(self):
        """Count active daily summaries."""
        for record in self:
            record.telegram_summary_count = self.env['telegram.daily.summary'].search_count([
                ('active', '=', True)
            ])

    def action_test_telegram_connection(self):
        """Test the Telegram bot connection."""
        self.ensure_one()

        telegram = self.env['telegram.service']
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
