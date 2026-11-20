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
                          add_recipients=True, push=None, company_filter=True, fallback_kind='scheduled_report'):
        """Deliver one Odoo alert into the app. Never raises: an alert must not stop what sent it. Returns the
        messages created (empty when the kind is archived or nobody receives it).

        :param company_filter: False to reach the named ``users`` even without access to ``company`` (an owner
            told about their own cash box); the message still shows the company.
        :param fallback_kind: the kind used when ``kind`` does not exist (None: send without a kind)."""
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
                kind=kind_rec or None, title=title, body=self._dl_body_of(text), users=users,
                company=(company or None) if company_filter else None, file=file, url=url,
                sender=company.name or 'Odoo', origin=origin or 'odoo_alert', push=push)
            if messages and company and not company_filter:
                messages.write({'company_id': company.id})
            return messages
        except Exception:  # noqa: BLE001
            _logger.exception('DoniaLink App: alert "%s" not delivered', kind)
            return self.browse()


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
        """The closing report as ONE app message (summary with the discounted orders, sales PDF attached),
        whatever the Telegram route; Telegram as before unless switched off."""
        self.ensure_one()
        pdf = self._session_pdf_content()
        self.env['donialink.app.message']._dl_from_telegram(
            'pos_session', self._prepare_session_summary_message(single=True), self.company_id,
            file=('POS_Sales_%s.pdf' % self.name, pdf, 'application/pdf') if pdf else None,
            url='/odoo/pos.session/%s' % self.id)
        if self.company_id._telegram_off():
            return True
        return super(PosSession, self.with_context(dl_app_done=True))._send_session_report()


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _telegram_send_order_alerts(self, company, messages):
        """Cancelled / edited open orders: in the app at once (rolled back with the transaction), Telegram as
        before unless switched off."""
        if not messages:
            return
        Message = self.env['donialink.app.message']
        for text in messages:
            Message._dl_from_telegram('pos_order_alert', text, company)
        if company._telegram_off():
            return
        return super()._telegram_send_order_alerts(company, messages)
