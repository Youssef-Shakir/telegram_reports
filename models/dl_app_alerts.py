# -*- coding: utf-8 -*-
"""Every Telegram Reports alert lands in the DoniaLink App (/dl/app), with one notification kind per alert type
(choose who receives each one in DoniaLink App > Kinds). Telegram is optional: a copy through the company's own
bot when "Also send to Telegram" is on."""
import base64
import html
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

_TAG = re.compile(r'<[^>]+>')

# Telegram Reports kinds (context "telegram_kind") -> app kind codes
GROUP_KINDS = {
    'pos_session': 'pos_session',
    'pos_order_alert': 'pos_order_alert',
    'daily_summary': 'daily_summary',
    'finance_summary': 'finance_summary',
    'scheduled_report': 'scheduled_report',
    'order_now': 'order_now',
}


class DonialinkAppMessage(models.Model):
    _inherit = 'donialink.app.message'

    @api.model
    def _dl_title_of(self, text, default):
        """First line of a Telegram message, as plain text: the title of the app message."""
        for line in (text or '').splitlines():
            plain = ' '.join(html.unescape(_TAG.sub('', line)).split())
            if plain:
                return plain[:200]
        return default

    @api.model
    def _dl_body_of(self, text):
        """Telegram HTML keeps line breaks as new lines: the app needs <br/>."""
        if not text:
            return ''
        if _TAG.search(text):
            return text.replace('\r\n', '\n').replace('\n', '<br/>')
        return text

    @api.model
    def _dl_from_telegram(self, kind, text, company, file=None, title=None, users=None, url=None, origin=None,
                          add_recipients=True, push=None, company_filter=True, fallback_kind='scheduled_report',
                          html_body=None):
        """Deliver one Odoo alert into the app. Never raises: an alert must not stop what sent it. Returns the
        messages created (empty when the kind is archived or nobody receives it).

        :param company_filter: False to reach the named ``users`` even without access to ``company`` (an owner
            told about their own cash box); the message still shows the company.
        :param fallback_kind: the kind used when ``kind`` does not exist (None: send without a kind).
        :param html_body: the organized app card (HTML) instead of the Telegram text."""
        try:
            Kind = self.env['donialink.app.kind']
            kind_rec = Kind._get(kind) if kind else Kind
            if kind and not kind_rec and fallback_kind:
                kind_rec = Kind._get(fallback_kind)
            if kind_rec and not kind_rec.active:
                return self.browse()
            if users is not None and kind_rec and add_recipients:
                users = users | kind_rec._recipients(company or None)
            if users is not None and not users:
                return self.browse()
            title = title or self._dl_title_of(text, kind_rec.name or 'DoniaLink')
            messages = self.sudo().send(
                kind=kind_rec or None, title=title, body=html_body or self._dl_body_of(text), users=users,
                company=(company or None) if company_filter else None, file=file, url=url,
                sender=company.name or 'Odoo', origin=origin or 'odoo_alert', push=push)
            if messages and company and not company_filter:
                messages.write({'company_id': company.id})
            return messages
        except Exception:  # noqa: BLE001
            _logger.exception('DoniaLink App: alert "%s" not delivered', kind)
            return self.browse()


class DonialinkAppKind(models.Model):
    _inherit = 'donialink.app.kind'

    @api.model
    def _dl_printer_kind_recipients(self):
        """At install: the printer alerts go to the people who receive the cancelled orders."""
        printer = self.env.ref('telegram_reports.kind_printer_alert', raise_if_not_found=False)
        orders = self.env.ref('telegram_reports.kind_pos_order_alert', raise_if_not_found=False)
        if printer and orders and not (printer.recipient_ids or printer.recipient_group_ids or printer.role_ids):
            printer.write({'recipient_ids': [(6, 0, orders.recipient_ids.ids)],
                           'recipient_group_ids': [(6, 0, orders.recipient_group_ids.ids)],
                           'role_ids': [(6, 0, orders.role_ids.ids)]})


class TelegramService(models.AbstractModel):
    """Every message of Telegram Reports also goes to the DoniaLink App; Telegram itself can be switched off."""
    _inherit = 'telegram.service'

    def _dl_app_kind(self):
        kind = self.env.context.get('telegram_kind') or self.DEFAULT_KIND
        return GROUP_KINDS.get(kind, 'scheduled_report') if kind != 'test' else None

    def _dl_app_deliver(self, text, file=None, title=None):
        kind = self._dl_app_kind()
        if not kind or self.env.context.get('dl_app_done'):
            return
        self.env['donialink.app.message']._dl_from_telegram(kind, text, self._company(), file=file, title=title)

    def _telegram_off(self):
        return self._company()._telegram_off()

    def send_message(self, text, chat_id=None, parse_mode='HTML'):
        self._dl_app_deliver(text)
        if self._telegram_off():
            return True
        return super(TelegramService, self.with_context(dl_app_done=True)).send_message(
            text, chat_id=chat_id, parse_mode=parse_mode)

    def send_document(self, document, filename, chat_id=None, caption=None):
        content = document
        if isinstance(content, str):
            content = base64.b64decode(content)
        self._dl_app_deliver(caption or filename, file=(filename, content, None), title=None)
        if self._telegram_off():
            return True
        return super(TelegramService, self.with_context(dl_app_done=True)).send_document(
            document, filename, chat_id=chat_id, caption=caption)

    def send_photo(self, image, filename, chat_id=None, caption=None):
        self._dl_app_deliver(caption or filename, file=(filename, image, 'image/jpeg'))
        if self._telegram_off():
            return True
        return super(TelegramService, self.with_context(dl_app_done=True)).send_photo(
            image, filename, chat_id=chat_id, caption=caption)

    def send_with_document(self, text, document=None, filename=None):
        self._dl_app_deliver(text, file=(filename or 'report.pdf', document, 'application/pdf') if document else None)
        if self._telegram_off():
            return True
        return super(TelegramService, self.with_context(dl_app_done=True)).send_with_document(
            text, document=document, filename=filename)


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _send_session_report(self):
        """The closing report as ONE organized app message (figures, payments, cash drawer, every movement of
        the session, the discount table, top products; sales PDF attached), whatever the Telegram route;
        Telegram as before unless switched off."""
        self.ensure_one()
        pdf = self._session_pdf_content()
        title, card = self._dl_app_session_card()
        self.env['donialink.app.message']._dl_from_telegram(
            'pos_session', self._prepare_session_summary_message(single=True), self.company_id,
            title=title, html_body=card,
            file=('POS_Sales_%s.pdf' % self.name, pdf, 'application/pdf') if pdf else None,
            url='/odoo/pos.session/%s' % self.id)
        if self.company_id._telegram_off():
            return True
        return super(PosSession, self.with_context(dl_app_done=True))._send_session_report()


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _schedule_telegram_cancel_messages(self, orders):
        """A cancelled order: an organized card in the app (products, amount, who, why), Telegram as before."""
        if orders and orders[0].company_id.sudo().telegram_send_on_order_cancel:
            Message = self.env['donialink.app.message']
            for order in orders:
                title, card = order._dl_app_cancel_card()
                Message._dl_from_telegram('pos_order_alert', title, order.company_id, title=title, html_body=card,
                                          url='/odoo/pos.order/%s' % order.id)
        return super(PosOrder, self.with_context(dl_app_done=True))._schedule_telegram_cancel_messages(orders)

    def _telegram_order_edit_alert(self, logs):
        """Items removed from an open order: an organized card in the app, Telegram as before."""
        if logs and self.company_id.sudo().telegram_send_on_order_cancel:
            title, card = self._dl_app_edit_card(logs)
            self.env['donialink.app.message']._dl_from_telegram(
                'pos_order_alert', title, self.company_id, title=title, html_body=card,
                url='/odoo/pos.order/%s' % self.id)
        return super(PosOrder, self.with_context(dl_app_done=True))._telegram_order_edit_alert(logs)

    def _telegram_send_order_alerts(self, company, messages):
        """Cancelled / edited open orders: in the app at once (rolled back with the transaction), Telegram as
        before unless switched off."""
        if not messages:
            return
        if not self.env.context.get('dl_app_done'):   # the organized cards above are already in the app
            Message = self.env['donialink.app.message']
            for text in messages:
                Message._dl_from_telegram('pos_order_alert', text, company)
        if company._telegram_off():
            return
        return super()._telegram_send_order_alerts(company, messages)
