# -*- coding: utf-8 -*-
"""Organized DoniaLink App cards for the POS alerts (Telegram keeps its own text messages):
- the session closing: key figures, payments, cash drawer, every movement of the session in time order
  (expenses, deposits, discounts, cancelled and edited orders), the discount table, top products, the reports;
- a cancelled order, an edited open order.
The HTML uses only tags and classes the app styles (.dl-rep*), nothing the message sanitizer removes."""
from html import escape

from odoo import fields, models


def esc(value):
    return escape(str(value if value not in (None, False) else ''), quote=True)


def table(head, rows, foot=None):
    """head: [label | (label, css)], rows: [[cell | (cell, css)]] -- cells already escaped HTML."""
    def cell(tag, value):
        if isinstance(value, tuple):
            return f'<{tag} class="{value[1]}">{value[0]}</{tag}>'
        return f'<{tag}>{value}</{tag}>'
    out = ['<div class="dl-rep-scroll"><table class="dl-rep-table">']
    if head:
        out.append('<thead><tr>' + ''.join(cell('th', h) for h in head) + '</tr></thead>')
    out.append('<tbody>' + ''.join('<tr>' + ''.join(cell('td', c) for c in row) + '</tr>' for row in rows) + '</tbody>')
    if foot:
        out.append('<tfoot><tr>' + ''.join(cell('td', c) for c in foot) + '</tr></tfoot>')
    out.append('</table></div>')
    return ''.join(out)


def section(title, content):
    return f'<h4 class="dl-rep-h">{esc(title)}</h4>{content}' if content else ''


def kpis(items):
    """[(label, value, tone)] tone: '' | 'neg' | 'pos'."""
    return '<div class="dl-rep-kpis">' + ''.join(
        f'<div class="dl-rep-kpi {tone}"><small>{esc(label)}</small><b>{esc(value)}</b></div>'
        for label, value, tone in items) + '</div>'


def chips(items):
    return '<p class="dl-rep-meta">' + ''.join(f'<span>{esc(i)}</span>' for i in items if i) + '</p>'


def card(lead, *parts):
    return f'<div class="dl-rep"><p class="dl-rep-lead">{esc(lead)}</p>' + ''.join(p for p in parts if p) + '</div>'


def signed(money, amount):
    return (esc(('+' if amount > 0 else '−') + money(abs(amount))), 'num ' + ('pos' if amount > 0 else 'neg'))


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _dl_hour(self, value):
        return fields.Datetime.context_timestamp(self, value).strftime('%H:%M') if value else '--:--'

    def _dl_app_movements(self, orders, discounts):
        """Every movement of the session, in time order: (datetime, icon, type, details, signed amount).
        Other modules may add theirs (super() + their rows)."""
        rows = []
        prefix = f"{self.name}-"
        for line in self.statement_line_ids:
            label = line.payment_ref or ''
            if not label.startswith(prefix):
                continue   # the lines Odoo adds at closing (cash difference)
            text = label[len(prefix):].split('-', 1)[-1] or label
            rows.append((line.create_date, '💸' if line.amount < 0 else '📥',
                         'مصروف / سحب' if line.amount < 0 else 'إيداع', text, line.amount))
        by_ref = {order._dl_ref(): order for order in orders}
        for e in discounts:
            order = by_ref.get(e['ref'])
            details = ' · '.join(filter(None, [f"#{e['ref']}", e['table'] and f"طاولة {e['table']}", e['employee'],
                                               e['free'] and 'مجاني بالكامل']))
            rows.append((order.date_order if order else self.stop_at, '🏷', 'خصم', details, -e['total']))
        for order in self.order_ids.filtered(lambda o: o.state == 'cancel' and o.lines):
            info = order._dl_cancel_facts()
            details = ' · '.join(filter(None, [f"#{order._dl_ref()}", info['table'] and f"طاولة {info['table']}",
                                               info['by'], info['reason']]))
            rows.append((info['when'], '🚫', 'طلب ملغى', details, -order.amount_total))
        if 'pos.order.edit.log' in self.env:
            for log in self.env['pos.order.edit.log'].sudo().search([('session_id', '=', self.id)], order='date'):
                change = 'حذف' if not log.qty_after else f"{log.qty_before:g} ← {log.qty_after:g}"
                details = ' · '.join(filter(None, [f"#{log.order_id._dl_ref()}", f"{log.product_name}: {change}",
                                                   log.edited_by, log.reason]))
                rows.append((log.date, '✂️', 'تعديل طلب', details, -log.amount))
        return sorted(rows, key=lambda r: r[0] or fields.Datetime.now())

    def _dl_app_session_card(self):
        """(title, html) of the closing report for the app."""
        self.ensure_one()
        money = self._telegram_money
        currency = self.currency_id or self.company_id.currency_id
        cash_control = self.config_id.cash_control
        orders = self.order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
        sales = sum(orders.mapped('amount_total'))
        count = len(orders)
        discounts = self._compute_discount_entries(orders)
        discount_total = sum(e['total'] for e in discounts)
        moves = self._telegram_cash_moves() if cash_control else []
        cash_out = -sum(a for _label, a in moves if a < 0)
        cash_in = sum(a for _label, a in moves if a > 0)
        difference = (self.cash_register_balance_end_real - self.cash_register_balance_end) if cash_control else 0.0
        no_difference = currency.is_zero(difference)

        lead = [f"المبيعات {money(sales)}", f"{count} طلب"]
        if discount_total:
            lead.append(f"خصومات {money(discount_total)}")
        if cash_out:
            lead.append(f"مصاريف {money(cash_out)}")
        if cash_control and not no_difference:
            lead.append(f"{'عجز' if difference < 0 else 'زيادة'} {money(abs(difference))}")

        tiles = [('المبيعات', money(sales), ''), ('الطلبات', str(count), ''),
                 ('المتوسط', money(sales / count) if count else '—', ''),
                 ('الخصومات', money(discount_total), 'neg' if discount_total else '')]
        if cash_control:
            tiles.append(('المصاريف', money(cash_out), 'neg' if cash_out else ''))
            tiles.append(('فرق الصندوق', 'لا يوجد', 'pos') if no_difference else
                         ('عجز' if difference < 0 else 'زيادة', money(abs(difference)), 'neg' if difference < 0 else 'pos'))

        payments = {}
        for payment in orders.payment_ids:
            name = payment.payment_method_id.name
            payments[name] = payments.get(name, 0.0) + payment.amount
        payments_html = section('💳 الدفع', table(
            ['الطريقة', ('المبلغ', 'num')],
            [[esc(m), (esc(money(a)), 'num')] for m, a in sorted(payments.items(), key=lambda x: -x[1])],
            foot=['المجموع', (esc(money(sum(payments.values()))), 'num')])) if payments else ''

        drawer_html = ''
        if cash_control:
            rows = [['الافتتاح', (esc(money(self.cash_register_balance_start)), 'num')]]
            if cash_out:
                rows.append(['المصاريف (سحب)', signed(money, -cash_out)])
            if cash_in:
                rows.append(['إيداع', signed(money, cash_in)])
            rows += [['المتوقع', (esc(money(self.cash_register_balance_end)), 'num')],
                     ['المعدود', (esc(money(self.cash_register_balance_end_real)), 'num')]]
            foot = (['✅ لا يوجد فرق', ('0', 'num pos')] if no_difference else
                    ['🔴 عجز' if difference < 0 else '🟢 زيادة', signed(money, difference)])
            drawer_html = section('💵 الصندوق', table(None, rows, foot=foot))

        movements = self._dl_app_movements(orders, discounts)
        movements_html = section(f'🧭 حركات الجلسة ({len(movements)})', table(
            [('الوقت', 'num'), 'النوع', 'التفاصيل', ('المبلغ', 'num')],
            [[(self._dl_hour(when), 'num'), esc(f"{icon} {kind}"), esc(text), signed(money, amount)]
             for when, icon, kind, text, amount in movements])) if movements else ''

        discounts_html = ''
        if discounts:
            rows = []
            for e in discounts:
                details = ([f"خصم عام {e['global_pct']:.0f}%"] if e['global'] else []) + [
                    f"{i['qty']:g}× {i['name']} {i['percent']:g}%" for i in e['items']]
                note = e['global_note'] or e['order_note'] or next((i['note'] for i in e['items'] if i['note']), '')
                cell = '<br/>'.join(esc(d) for d in details)
                if note:
                    cell += f'<br/><small class="dl-rep-note">📝 {esc(note)}</small>'
                if e['free']:
                    cell += '<br/><b class="neg">🎁 مجاني بالكامل</b>'
                who = ' · '.join(filter(None, [e['table'] and f"طاولة {e['table']}", e['employee']]))
                order_cell = f"<b>#{esc(e['ref'])}</b>" + (f'<br/><small>{esc(who)}</small>' if who else '')
                if e['before']:
                    cell += f"<br/><small>قبل الخصم {esc(money(e['before']))} · المدفوع {esc(money(e['paid']))}</small>"
                rows.append([order_cell, cell, (esc(money(e['total'])), 'num neg')])
            discounts_html = section(f'🏷 جدول الخصومات ({len(discounts)})', table(
                ['الطلب', 'التفاصيل', ('الخصم', 'num')], rows,
                foot=['المجموع', f"<small>قبل الخصم {esc(money(sum(e['before'] for e in discounts)))}</small>",
                      (esc(money(discount_total)), 'num neg')]))

        top_html = ''
        if self.company_id.telegram_pos_close_top_products and orders:
            product_sales = {}
            for line in orders.lines.filtered('product_id'):
                product_sales[line.product_id.name] = product_sales.get(line.product_id.name, 0) + line.qty
            top = sorted(product_sales.items(), key=lambda x: -x[1])[:self.company_id.telegram_pos_close_top_count or 5]
            top_html = section('🏆 الأكثر مبيعاً', table(
                ['#', 'المنتج', ('الكمية', 'num')],
                [[str(i), esc(name), (f"{qty:,.0f}", 'num')] for i, (name, qty) in enumerate(top, 1)])) if top else ''

        reports = (['📄 تقرير مبيعات الجلسة (PDF): مرفق في الأسفل'] if self.company_id.telegram_pos_close_send_pdf else [])
        reports.append('🔗 الجلسة كاملة في أودو: زر الفتح في الأسفل')
        reports_html = section('📑 التقارير', '<ul class="dl-rep-list">' + ''.join(f'<li>{esc(r)}</li>' for r in reports) + '</ul>')
        state = '✅ تم إغلاق الجلسة' if self.state == 'closed' else f'📊 الحالة: {self.state}'

        html = card(' · '.join(lead),
                    chips([f"🏪 {self.config_id.name}", f"📋 {self.name}", f"👤 {self.user_id.name}",
                           f"🕐 {self._dl_hour(self.start_at)} ← {self._dl_hour(self.stop_at)}"]),
                    kpis(tiles), payments_html, drawer_html, movements_html, discounts_html, top_html, reports_html,
                    f'<p class="dl-rep-foot">{esc(state)}</p>')
        return f"إغلاق الجلسة: {self.config_id.name} — {self.name}", html


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _dl_ref(self):
        return (self.pos_reference or self.name or '').split('-')[-1]

    def _dl_money(self):
        return self.session_id._telegram_money if self.session_id else (lambda amount: f"{amount:,.2f}")

    def _dl_cancel_facts(self):
        """Plain (not escaped) facts of a cancelled order."""
        self.ensure_one()
        has = lambda name: name in self._fields and self[name]
        return {
            'when': has('cancel_date') or self.write_date or fields.Datetime.now(),
            'by': has('cancel_by') or (self.employee_id.name if has('employee_id') else '') or self.user_id.name,
            'reason': has('cancel_reason') or '',
            'table': str(self.table_id.table_number or '') if has('table_id') else '',
        }

    def _dl_app_cancel_card(self):
        self.ensure_one()
        money = self._dl_money()
        info = self._dl_cancel_facts()
        reason = info['reason'] or 'لم يتم إدخال سبب'
        html = card(
            f"طلب #{self._dl_ref()} · {money(self.amount_total)} · {reason}",
            chips([f"🏪 {self.config_id.name}", info['table'] and f"🪑 طاولة {info['table']}", f"👤 {info['by']}",
                   f"🕐 {fields.Datetime.context_timestamp(self, info['when']).strftime('%H:%M')}"]),
            kpis([('المبلغ', money(self.amount_total), 'neg'), ('المنتجات', str(len(self.lines)), '')]),
            section('🧾 المنتجات', table(
                [('الكمية', 'num'), 'المنتج', ('المبلغ', 'num')],
                [[(f"{line.qty:g}", 'num'), esc(line.full_product_name or line.product_id.name),
                  (esc(money(line.price_subtotal_incl)), 'num')] for line in self.lines],
                foot=['', 'المجموع', (esc(money(self.amount_total)), 'num neg')])),
            section('📝 السبب', f'<p class="dl-rep-note">{esc(reason)}</p>'))
        title = f"🚫 طلب ملغى #{self._dl_ref()}" + (f" — طاولة {info['table']}" if info['table'] else '')
        return title, html

    def _dl_app_edit_card(self, logs):
        self.ensure_one()
        money = self._dl_money()
        info = self._dl_cancel_facts()
        log = logs[0]
        removed = sum(logs.mapped('amount'))
        reasons = ' / '.join(sorted({item.reason for item in logs if item.reason})) or 'لم يتم إدخال سبب'
        html = card(
            f"طلب #{self._dl_ref()} · حُذف {money(removed)} · {reasons}",
            chips([f"🏪 {self.config_id.name}", info['table'] and f"🪑 طاولة {info['table']}",
                   f"👤 {log.edited_by or self.user_id.name}",
                   f"🕐 {fields.Datetime.context_timestamp(self, log.date).strftime('%H:%M')}"]),
            section('🧾 التغييرات', table(
                ['المنتج', ('قبل', 'num'), ('بعد', 'num'), ('المبلغ', 'num')],
                [[esc(item.product_name), (f"{item.qty_before:g}", 'num'),
                  ('حذف' if not item.qty_after else f"{item.qty_after:g}", 'num'), signed(money, -item.amount)]
                 for item in logs],
                foot=['المجموع', '', '', signed(money, -removed)])),
            section('📝 السبب', f'<p class="dl-rep-note">{esc(reasons)}</p>'))
        title = f"✂️ تعديل طلب #{self._dl_ref()}" + (f" — طاولة {info['table']}" if info['table'] else '')
        return title, html
