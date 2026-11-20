# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    """Telegram per company: optional, through the company's own bot. Every alert always goes to the DoniaLink
    App; Telegram is a copy for the groups that still want it."""
    _inherit = 'res.company'

    telegram_enabled = fields.Boolean(
        'Also Send to Telegram', default=False,
        help='Off: alerts only go to the DoniaLink App. On: also to the Telegram groups below, with the bot token.')
    telegram_bot_token = fields.Char('Telegram Bot Token', groups='base.group_system')
    telegram_default_chat_id = fields.Char('Telegram Group', help='Chat id of the group that gets every alert '
                                                                  '(unless a group is set for its kind).')
    telegram_chat_pos = fields.Char('Group for POS Sessions & Orders',
                                    help='Session closing reports, cancelled and edited orders. Empty: the main group.')
    telegram_chat_summary = fields.Char('Group for Summaries',
                                        help='Daily and financial summaries. Empty: the main group.')
    telegram_chat_reports = fields.Char('Group for Scheduled Reports', help='Empty: the main group.')
    telegram_chat_order_now = fields.Char('Group for Order Now', help='Empty: the main group.')
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

    def _telegram_off(self):
        """Nothing goes to Telegram for this company (the DoniaLink App still gets everything)."""
        company = self.sudo()
        return not (company.telegram_enabled and company.telegram_bot_token)
