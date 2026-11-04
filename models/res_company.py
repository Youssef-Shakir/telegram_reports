# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    """Telegram settings per company: each branch can have its own bot and chat, or send through DoniaLink."""
    _inherit = 'res.company'

    telegram_delivery = fields.Selection([
        ('bot', 'Own Telegram bot'),
        ('donialink', 'Through DoniaLink'),
    ], string='Telegram Delivery', default='bot', required=True,
        help="Own Telegram bot: this company's bot token and chat.\n"
             "Through DoniaLink: messages go to the DoniaLink Platform (DoniaLink Agent Connector, connected), "
             "which sends them to the groups set there for each kind of message.")
    telegram_bot_token = fields.Char('Telegram Bot Token', groups='base.group_system')
    telegram_default_chat_id = fields.Char('Telegram Default Chat ID')
    telegram_send_on_pos_close = fields.Boolean('Telegram: Send on POS Session Close')
    telegram_pos_close_top_products = fields.Boolean('Telegram: Include Top Products', default=True)
    telegram_pos_close_top_count = fields.Integer('Telegram: Top Products Count', default=5)
    telegram_pos_close_send_pdf = fields.Boolean('Telegram: Send PDF Report')
    telegram_send_on_order_cancel = fields.Boolean('Telegram: Send Cancelled Orders', default=True)
    # Order Now (Recipe Costing 18.0.4.8.0+): the ingredients to buy, once a day
    telegram_order_now = fields.Boolean('Telegram: Daily Order Now List')
    telegram_order_now_time = fields.Float('Telegram: Order Now Time', default=9.0,
                                           help='Local time (24-hour) to send the list; only sent when something is '
                                                'to order.')
    telegram_order_now_last = fields.Date('Telegram: Order Now Last Sent', readonly=True)

    @api.constrains('telegram_delivery')
    def _check_telegram_delivery(self):
        if 'donialink.agent.platform' in self.env:
            return
        if any(company.telegram_delivery == 'donialink' for company in self):
            raise ValidationError(_('To send through DoniaLink, install the DoniaLink Agent Connector first '
                                    '(or choose "Own Telegram bot").'))
