# -*- coding: utf-8 -*-
"""Daily "Order Now" message: the ingredients at or below their reorder point (Recipe Costing 18.0.4.8.0+), grouped by
supplier, with the quantity to order in the purchase unit, the stock on hand and the days left."""
import html
import logging
from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _num(value, digits=2):
    text = f"{value or 0:,.{digits}f}"
    return text.rstrip('0').rstrip('.') if '.' in text else text


class TelegramOrderNow(models.AbstractModel):
    _name = 'telegram.order.now'
    _description = 'Telegram Order Now List'

    @api.model
    def _available(self):
        return hasattr(self.env['product.product'], 'get_order_now_list')

    @api.model
    def _message(self, company):
        """The message for one company, or None when nothing is to order."""
        data = self.env['product.product'].with_company(company).sudo().get_order_now_list()
        items = data.get('items') or []
        if not items:
            return None
        groups = {}
        for item in items:  # most urgent first: each supplier's group in the order of its most urgent item
            groups.setdefault(item.get('vendor') or '', []).append(item)
        order = sorted(groups, key=lambda vendor: (not vendor, list(groups).index(vendor)))
        negative = sum(1 for i in items if i.get('negative_stock'))
        tz = pytz.timezone(company.partner_id.tz or self.env.user.tz or 'UTC')
        msg = f"🛒 <b>اطلب الآن</b> — {html.escape(company.name)}\n"
        msg += f"📅 {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"{len(items)} مكوّن وصل إلى حدّ الطلب"
        msg += f"، منها {negative} بمخزون سالب ⚠️\n" if negative else "\n"
        for vendor in order:
            rows = groups[vendor]
            msg += f"\n🏪 <b>{html.escape(vendor) if vendor else 'بدون مورد'}</b> ({len(rows)})\n"
            for item in rows:
                quantity = item.get('order_qty_purchase_uom')
                unit = item.get('purchase_uom') or item.get('uom') or ''
                if quantity is None:
                    quantity, unit = item.get('order_qty'), item.get('uom') or ''
                msg += (f"• {html.escape(item.get('name') or '')}: <b>{_num(quantity)} {html.escape(unit)}</b>"
                        f" · المتوفر {_num(item.get('on_hand'))} {html.escape(item.get('uom') or '')}")
                if item.get('negative_stock'):
                    msg += " ⚠️ سالب"
                if (item.get('on_hand') or 0) <= 0:
                    msg += " · نفد"  # "0 days left" on every empty item is noise
                elif item.get('days_left') is not None:
                    msg += f" · يكفي {_num(item['days_left'], 1)} يوم"
                msg += "\n"
        return msg

    @api.model
    def _send(self, company, force=False):
        """Send the list to the company's chat (or through DoniaLink); True when sent."""
        if not self._available():
            raise UserError(_('Order Now needs Recipe Costing 18.0.4.8.0 or later.'))
        message = self._message(company)
        if not message:
            return False
        telegram = self.env['telegram.service'].with_company(company).with_context(telegram_kind='order_now')
        telegram.send_message(message)
        company.sudo().telegram_order_now_last = fields.Date.context_today(self.with_company(company))
        return True

    @api.model
    def _cron_send_order_now(self):
        """Every 15 minutes: each company whose time has come today (its timezone) and that wasn't sent today."""
        if not self._available():
            return True
        for company in self.env['res.company'].sudo().search([('telegram_order_now', '=', True)]):
            tz = pytz.timezone(company.partner_id.tz or self.env.user.tz or 'UTC')
            now = datetime.now(tz)
            if now.hour + now.minute / 60 < company.telegram_order_now_time:
                continue
            if company.telegram_order_now_last == now.date():
                continue
            try:
                if not self._send(company):  # nothing to order: checked for today all the same
                    company.telegram_order_now_last = now.date()
            except Exception as e:
                _logger.error("Order Now for %s failed: %s", company.name, e)
        return True
