# -*- coding: utf-8 -*-
import html
import logging
import threading

import requests

from odoo import api, fields, models

from .telegram_service import TELEGRAM_API_URL

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    """Send a Telegram message when a POS order is cancelled."""
    _inherit = 'pos.order'

    def _telegram_cancel_info(self):
        """Readable details of a cancelled order (HTML-escaped for Telegram).

        The cancel reason fields come from dev_pos_access_rights when it is
        installed; without it the reason is simply left empty.
        """
        self.ensure_one()
        esc = lambda value: html.escape(value or '', quote=False)
        has_reason = 'cancel_reason' in self._fields
        ref = (self.pos_reference or self.name or '').split('-')[-1]
        table = self.table_id.table_number if 'table_id' in self._fields and self.table_id else ''
        employee = self.employee_id.name if 'employee_id' in self._fields and self.employee_id else ''
        when = (has_reason and self.cancel_date) or self.write_date or fields.Datetime.now()
        return {
            'ref': esc(ref),
            'table': esc(str(table or '')),
            'by': esc((has_reason and self.cancel_by) or employee or self.user_id.name),
            'time': fields.Datetime.context_timestamp(self, when).strftime('%H:%M'),
            'reason': esc(has_reason and self.cancel_reason or ''),
            'items': [
                f"{line.qty:g}x {esc(line.full_product_name or line.product_id.name)}"
                for line in self.lines
            ],
        }

    def _prepare_telegram_cancel_message(self):
        self.ensure_one()
        info = self._telegram_cancel_info()
        currency = self.currency_id
        symbol = currency.symbol or currency.name

        msg = "🚫 <b>طلب ملغى</b>\n"
        msg += f"📋 <b>الطلب:</b> #{info['ref']}"
        if info['table']:
            msg += f" — طاولة {info['table']}"
        msg += "\n"
        msg += f"👤 <b>بواسطة:</b> {info['by']}\n"
        msg += f"🕐 <b>الوقت:</b> {info['time']}\n"
        msg += f"💰 <b>المبلغ:</b> {self.amount_total:,.2f} {symbol}\n"
        if info['items']:
            msg += "🧾 <b>المنتجات:</b>\n"
            for item in info['items'][:20]:
                msg += f"  • {item}\n"
            if len(info['items']) > 20:
                msg += f"  ... و {len(info['items']) - 20} منتجات أخرى\n"
        msg += f"📝 <b>السبب:</b> {info['reason'] or 'لم يتم إدخال سبب'}\n"
        msg += f"📍 {html.escape(self.config_id.name or '', quote=False)}"
        return msg

    def action_pos_order_cancel(self):
        # Only orders that really get cancelled now (core cancels drafts only),
        # and only ones with items: empty orders (e.g. unbooking a table) are noise.
        to_notify = self.filtered(lambda o: o.state == 'draft' and o.lines)
        result = super().action_pos_order_cancel()
        try:
            self._schedule_telegram_cancel_messages(to_notify.filtered(lambda o: o.state == 'cancel'))
        except Exception:
            _logger.exception("Could not prepare Telegram cancel notification")
        return result

    def _schedule_telegram_cancel_messages(self, orders):
        if not orders:
            return
        company = orders[0].company_id.sudo()
        if not company.telegram_send_on_order_cancel:
            return
        self._telegram_send_order_alerts(company, [order._prepare_telegram_cancel_message() for order in orders])

    def _telegram_order_edit_alert(self, logs):
        """Lines reduced / removed from an open order with the reason (dev_pos_access_rights).
        Sent with the cancelled orders setting, since it is the same kind of alert."""
        self.ensure_one()
        company = self.company_id.sudo()
        if not logs or not company.telegram_send_on_order_cancel:
            return
        self._telegram_send_order_alerts(company, [self._prepare_telegram_edit_message(logs)])

    def _prepare_telegram_edit_message(self, logs):
        self.ensure_one()
        esc = lambda value: html.escape(value or '', quote=False)
        info = self._telegram_cancel_info()
        symbol = self.currency_id.symbol or self.currency_id.name
        log = logs[0]
        msg = "✂️ <b>تعديل طلب مفتوح</b>\n"
        msg += f"📋 <b>الطلب:</b> #{info['ref']}"
        if info['table']:
            msg += f" — طاولة {info['table']}"
        msg += "\n"
        msg += f"👤 <b>بواسطة:</b> {esc(log.edited_by) or info['by']}\n"
        msg += f"🕐 <b>الوقت:</b> {fields.Datetime.context_timestamp(self, log.date).strftime('%H:%M')}\n"
        msg += "🧾 <b>المنتجات:</b>\n"
        for item in logs:
            action = "حذف" if not item.qty_after else f"{item.qty_before:g} ← {item.qty_after:g}"
            msg += f"  • {esc(item.product_name)}: {action} (−{item.qty_removed:g}, {item.amount:,.2f} {symbol})\n"
        reasons = {item.reason for item in logs if item.reason}
        msg += f"📝 <b>السبب:</b> {esc(' / '.join(reasons)) or 'لم يتم إدخال سبب'}\n"
        msg += f"📍 {esc(self.config_id.name)}"
        return msg

    def _telegram_send_order_alerts(self, company, messages):
        """Send order alerts (cancelled / edited orders) to Telegram once the transaction is committed."""
        if not messages:
            return
        if company.telegram_delivery == 'donialink':
            # through the platform, after the commit (with its own cursor: this one is closed by then)
            dbname, uid, company_id = self.env.cr.dbname, self.env.uid, company.id

            def send_through_donialink():
                try:
                    with self.env.registry.cursor() as cr:
                        env = api.Environment(cr, uid, {})
                        service = env['telegram.service'].with_company(company_id).with_context(
                            telegram_kind='pos_session')
                        for text in messages:
                            service.send_message(text)
                except Exception:
                    _logger.exception("Telegram order alert through DoniaLink failed (%s)", dbname)

            self.env.cr.postcommit.add(send_through_donialink)
            return
        token, chat_id = company.telegram_bot_token, company.telegram_default_chat_id
        if not token or not chat_id:
            return

        def send():
            url = TELEGRAM_API_URL.format(token=token, method='sendMessage')
            for text in messages:
                try:
                    response = requests.post(url, data={
                        'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                    }, timeout=15)
                    if not response.json().get('ok'):
                        _logger.error("Telegram order alert failed: %s", response.text[:300])
                except Exception as e:
                    _logger.error("Telegram order alert failed: %s", e)

        # Only after the change is committed (nothing is sent if it is rolled back),
        # and in a thread so the POS doesn't wait for Telegram.
        self.env.cr.postcommit.add(lambda: threading.Thread(target=send, daemon=True).start())
