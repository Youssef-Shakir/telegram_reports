# -*- coding: utf-8 -*-
import html
import logging
import os
import subprocess
import tempfile
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import find_in_path

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    """Extend POS Session to send Telegram notification on close."""
    _inherit = 'pos.session'

    telegram_sent = fields.Boolean('Telegram Sent', default=False, copy=False)

    def action_send_telegram_summary(self):
        """Manual button to send session summary to Telegram."""
        self.ensure_one()

        try:
            message = self._prepare_session_summary_message()
            telegram = self.env['telegram.service']
            telegram.send_message(message)
            self._send_discount_table()

            # Also send PDF if enabled
            self._send_session_pdf_report()

            self.telegram_sent = True

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Session summary sent to Telegram!'),
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(_('Failed to send: %s') % str(e))

    def _send_session_pdf_report(self):
        """Send POS session PDF report to Telegram."""
        self.ensure_one()

        # Check if PDF sending is enabled
        send_pdf = self.env['ir.config_parameter'].sudo().get_param(
            'telegram_reports.pos_close_send_pdf', 'False'
        )
        if send_pdf != 'True':
            return False

        try:
            # Use the standard POS sale details report
            report = self.env.ref('point_of_sale.sale_details_report', raise_if_not_found=False)

            if not report:
                _logger.warning("Sale details report not found (point_of_sale.sale_details_report)")
                return False

            _logger.info("Using POS sale details report for session: %s", self.name)

            # Prepare data for the report (same format as the wizard uses)
            data = {
                'date_start': self.start_at,
                'date_stop': self.stop_at or fields.Datetime.now(),
                'config_ids': [self.config_id.id],
            }

            # Generate PDF using the data-driven report
            telegram = self.env['telegram.service']
            success = telegram.send_pos_sale_details_report(
                self,
                data,
                caption=f"📋 تقرير مبيعات الجلسة: {self.name}",
                filename=f"POS_Sales_{self.name}.pdf"
            )
            return success

        except Exception as e:
            _logger.error("Failed to send PDF for session %s: %s", self.name, str(e))
            return False

    def _send_telegram_session_summary(self):
        """Send session summary to Telegram (called on session close)."""
        self.ensure_one()

        # Check if feature is enabled
        send_on_close = self.env['ir.config_parameter'].sudo().get_param(
            'telegram_reports.send_on_pos_close', 'False'
        )
        if send_on_close != 'True':
            _logger.info("Telegram send on POS close is disabled")
            return False

        try:
            # Send text summary
            message = self._prepare_session_summary_message()
            telegram = self.env['telegram.service']
            telegram.send_message(message)
            _logger.info("Sent Telegram text summary for POS session: %s", self.name)
            self._send_discount_table()

            # Send PDF report if enabled
            self._send_session_pdf_report()

            self.telegram_sent = True
            return True

        except Exception as e:
            _logger.error("Failed to send Telegram summary for session %s: %s", self.name, str(e))
            return False

    def _prepare_session_summary_message(self):
        """Prepare the session summary message."""
        self.ensure_one()

        currency = self.currency_id or self.company_id.currency_id
        symbol = currency.symbol or currency.name

        # Get orders for this session
        orders = self.order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
        total_sales = sum(orders.mapped('amount_total'))
        total_orders = len(orders)

        # Build message
        msg = f"🏪 <b>تقرير جلسة نقطة البيع</b>\n"
        msg += f"📋 {self.name}\n"
        msg += f"{'─' * 25}\n\n"

        # Session info
        msg += f"👤 <b>الكاشير:</b> {self.user_id.name}\n"
        msg += f"📍 <b>نقطة البيع:</b> {self.config_id.name}\n"

        if self.start_at:
            start_time = fields.Datetime.context_timestamp(self, self.start_at)
            msg += f"🕐 <b>وقت البدء:</b> {start_time.strftime('%H:%M')}\n"
        if self.stop_at:
            stop_time = fields.Datetime.context_timestamp(self, self.stop_at)
            msg += f"🕐 <b>وقت الإغلاق:</b> {stop_time.strftime('%H:%M')}\n"

        msg += f"\n{'─' * 25}\n"
        msg += f"💰 <b>إجمالي المبيعات:</b> {total_sales:,.2f} {symbol}\n"
        msg += f"🧾 <b>عدد الطلبات:</b> {total_orders}\n"

        if total_orders > 0:
            avg_order = total_sales / total_orders
            msg += f"📈 <b>متوسط الطلب:</b> {avg_order:,.2f} {symbol}\n"

        # Order details
        if orders:
            msg += f"\n📝 <b>تفاصيل الطلبات:</b>\n"
            for order in orders[:10]:  # Limit to 10 orders to avoid too long message
                order_time = fields.Datetime.context_timestamp(self, order.date_order)
                msg += f"  • {order.name}: {order.amount_total:,.2f} {symbol} ({order_time.strftime('%H:%M')})\n"

            if len(orders) > 10:
                msg += f"  ... و {len(orders) - 10} طلبات أخرى\n"

        # Payment summary
        if orders:
            msg += f"\n💳 <b>طرق الدفع:</b>\n"
            payments = {}
            for order in orders:
                for payment in order.payment_ids:
                    method = payment.payment_method_id.name
                    payments[method] = payments.get(method, 0) + payment.amount

            if payments:
                for method, amount in sorted(payments.items(), key=lambda x: -x[1]):
                    msg += f"  • {method}: {amount:,.2f} {symbol}\n"
            else:
                msg += f"  • لا توجد مدفوعات\n"

        # Cancelled orders with their reason (empty orders are skipped)
        cancelled = self.order_ids.filtered(lambda o: o.state == 'cancel' and o.lines)
        if cancelled:
            msg += f"\n🚫 <b>الطلبات الملغاة ({len(cancelled)}):</b>\n"
            for order in cancelled.sorted('date_order')[:15]:
                info = order._telegram_cancel_info()
                msg += f"  • #{info['ref']}"
                if info['table']:
                    msg += f" طاولة {info['table']}"
                msg += f" — {order.amount_total:,.2f} {symbol} — {info['by']} ({info['time']})\n"
                msg += f"    📝 {info['reason'] or 'لم يتم إدخال سبب'}\n"
            if len(cancelled) > 15:
                msg += f"  ... و {len(cancelled) - 15} طلبات أخرى\n"

        msg += self._prepare_discount_section(orders, symbol)

        # Cash control
        if self.config_id.cash_control:
            msg += f"\n💵 <b>النقدية:</b>\n"
            msg += f"  • الافتتاحي: {self.cash_register_balance_start:,.2f} {symbol}\n"
            msg += f"  • النهائي: {self.cash_register_balance_end_real:,.2f} {symbol}\n"
            difference = self.cash_register_balance_end_real - self.cash_register_balance_end
            if abs(difference) > 0.01:
                msg += f"  • الفرق: {difference:,.2f} {symbol} ⚠️\n"

        # Top products
        include_top = self.env['ir.config_parameter'].sudo().get_param(
            'telegram_reports.pos_close_top_products', 'True'
        )
        if include_top == 'True' and orders:
            product_sales = {}
            for order in orders:
                for line in order.lines:
                    if line.product_id:
                        product = line.product_id.name
                        product_sales[product] = product_sales.get(product, 0) + line.qty

            if product_sales:
                msg += f"\n🏆 <b>المنتجات الأكثر مبيعاً:</b>\n"
                top_count = int(self.env['ir.config_parameter'].sudo().get_param(
                    'telegram_reports.pos_close_top_count', '5'
                ))
                top_products = sorted(product_sales.items(), key=lambda x: -x[1])[:top_count]
                for i, (product, qty) in enumerate(top_products, 1):
                    msg += f"  {i}. {product}: {qty:,.0f}\n"

        msg += f"\n{'─' * 25}\n"

        if self.state == 'closed':
            msg += f"✅ تم الإغلاق بنجاح"
        else:
            msg += f"📊 حالة الجلسة: {self.state}"

        return msg

    def _compute_discount_entries(self, orders):
        """Discounted orders of the session: global discount (pos_discount
        product line) and per-line discounts, biggest first."""
        config = self.config_id
        discount_product = config.discount_product_id if 'discount_product_id' in config._fields else False

        def undiscounted(line):
            taxes = line.tax_ids_after_fiscal_position
            if taxes:
                return taxes.compute_all(
                    line.price_unit, line.order_id.currency_id, line.qty,
                    product=line.product_id, partner=line.order_id.partner_id,
                )['total_included']
            return line.price_unit * line.qty

        def note_of(record, *fields_):
            parts = [' '.join(str(record[f] or '').split()) for f in fields_ if f in record._fields]
            return ' / '.join(p for p in parts if p)

        entries = []
        for order in orders:
            global_amount, items, line_amount, before = 0.0, [], 0.0, 0.0
            global_notes = []
            for line in order.lines:
                if discount_product and line.product_id == discount_product:
                    global_amount += -line.price_subtotal_incl
                    if note_of(line, 'note', 'customer_note'):
                        global_notes.append(note_of(line, 'note', 'customer_note'))
                    continue
                full = undiscounted(line)
                before += full
                if line.discount:
                    amount = full - line.price_subtotal_incl
                    line_amount += amount
                    items.append({
                        'name': line.full_product_name or line.product_id.name,
                        'qty': line.qty, 'percent': line.discount, 'amount': amount,
                        'note': note_of(line, 'note', 'customer_note'),
                    })
            total = global_amount + line_amount
            if abs(total) < 0.01:
                continue
            employee = ''
            if 'x_original_employee_id' in order._fields and order.x_original_employee_id:
                employee = order.x_original_employee_id.name
            elif 'employee_id' in order._fields and order.employee_id:
                employee = order.employee_id.name
            entries.append({
                'ref': (order.pos_reference or order.name or '').split('-')[-1],
                'table': str(order.table_id.table_number or '') if 'table_id' in order._fields and order.table_id else '',
                'employee': employee,
                'before': before, 'paid': order.amount_total, 'total': total,
                'global': global_amount,
                'global_pct': (global_amount / before * 100) if before else 0,
                'items': items,
                'global_note': ' / '.join(global_notes),
                'order_note': note_of(order, 'general_note'),
                'free': abs(order.amount_total) < 0.01,
            })
        return sorted(entries, key=lambda e: -e['total'])

    def _prepare_discount_section(self, orders, symbol):
        """One line in the text message; the details go in the table image."""
        entries = self._compute_discount_entries(orders)
        if not entries:
            return ''
        total = sum(e['total'] for e in entries)
        free = sum(1 for e in entries if e['free'])
        msg = f"\n🏷 <b>الخصومات:</b> {total:,.0f} {symbol} — {len(entries)} طلب"
        if free:
            msg += f" (منها {free} مجاني بالكامل)"
        return msg + "\n  📊 التفاصيل في جدول الخصومات أدناه\n"

    def _render_discount_table_image(self, entries, symbol):
        """Render the discount details as a JPEG table (Arabic, right to left)."""
        esc = lambda value: html.escape(str(value or ''), quote=True)
        total = sum(e['total'] for e in entries)
        rows = []
        for i, e in enumerate(entries, 1):
            kinds = []
            if e['global']:
                kinds.append(f"خصم عام {e['global_pct']:.0f}%")
            if e['items']:
                kinds.append("خصم على المنتجات")
            note_html = lambda n: f"<div class='note'>ملاحظة: {esc(n)}</div>" if n else ''
            details = ''.join(
                f"<div>{it['qty']:g}× {esc(it['name'])} <b>{it['percent']:g}%</b>"
                f" <span class='num'>{it['amount']:,.0f}</span></div>{note_html(it['note'])}"
                for it in e['items'])
            if e['global']:
                details = (f"<div>خصم عام على الفاتورة <b>{e['global_pct']:.0f}%</b></div>"
                           f"{note_html(e['global_note'])}" + details)
            if e['order_note']:
                details += f"<div class='note order-note'>ملاحظة الطلب: {esc(e['order_note'])}</div>"
            rows.append(
                f"<tr class='{'free' if e['free'] else ''}'>"
                f"<td class='num'>{i}</td><td class='num'>#{esc(e['ref'])}</td><td class='num'>{esc(e['table'])}</td>"
                f"<td>{esc(e['employee'])}</td><td>{' + '.join(kinds)}{'<br><b>مجاني بالكامل</b>' if e['free'] else ''}</td>"
                f"<td class='details'>{details}</td>"
                f"<td class='num'>{e['before']:,.0f}</td><td class='num'>{e['paid']:,.0f}</td>"
                f"<td class='num amount'>{e['total']:,.0f}</td></tr>")
        page = f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><style>
body {{ font-family: 'DejaVu Sans', sans-serif; margin: 0; padding: 18px; background: #ffffff; color: #1d2433; font-size: 15px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} .sub {{ color: #5b6475; margin-bottom: 12px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #c9ced8; padding: 6px 8px; vertical-align: top; text-align: right; }}
th {{ background: #1f3a68; color: #ffffff; font-size: 14px; }}
tr:nth-child(even) td {{ background: #f4f6fa; }}
tr.free td {{ background: #fdeaea; }}
.num {{ text-align: center; white-space: nowrap; direction: ltr; }}
.amount {{ font-weight: bold; color: #a12424; }}
.details {{ font-size: 13px; }} .details div {{ padding: 1px 0; }}
.note {{ color: #8a4b00; background: #fff4dc; border-radius: 3px; padding: 1px 6px !important; margin: 0 14px 3px 0; font-size: 12.5px; display: block; }}
.order-note {{ margin-top: 4px; }}
tfoot td {{ background: #e3e8f2; font-weight: bold; font-size: 16px; }}
</style></head><body>
<h1>جدول الخصومات — {esc(self.name)}</h1>
<div class="sub">{esc(self.config_id.name)} · {len(entries)} طلب · المبالغ بـ {esc(symbol)} · الأحمر = مجاني بالكامل</div>
<table><thead><tr><th>#</th><th>الطلب</th><th>الطاولة</th><th>الموظف</th><th>نوع الخصم</th><th>التفاصيل</th>
<th>قبل الخصم</th><th>المدفوع</th><th>الخصم</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><td colspan="6">المجموع</td><td class="num">{sum(e['before'] for e in entries):,.0f}</td>
<td class="num">{sum(e['paid'] for e in entries):,.0f}</td><td class="num amount">{total:,.0f}</td></tr></tfoot>
</table></body></html>"""
        wkhtmltoimage = find_in_path('wkhtmltoimage')
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, 'discounts.html'), os.path.join(tmp, 'discounts.jpg')
            with open(src, 'w', encoding='utf-8') as f:
                f.write(page)
            subprocess.run([wkhtmltoimage, '--quiet', '--encoding', 'utf-8', '--width', '1100',
                            '--format', 'jpg', '--quality', '85', src, out], check=True, timeout=60)
            with open(out, 'rb') as f:
                return f.read()

    def _send_discount_table(self):
        """Send the discount table image after the text summary."""
        self.ensure_one()
        orders = self.order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
        entries = self._compute_discount_entries(orders)
        if not entries:
            return False
        currency = self.currency_id or self.company_id.currency_id
        symbol = currency.symbol or currency.name
        try:
            image = self._render_discount_table_image(entries, symbol)
            caption = f"🏷 جدول الخصومات — {html.escape(self.name)}"
            telegram = self.env['telegram.service']
            try:
                telegram.send_photo(image, f"Discounts_{self.name}.jpg", caption=caption)
            except Exception:
                # Very tall tables exceed Telegram's photo size/ratio limits:
                # send the same image as a file instead.
                telegram.send_document(image, f"Discounts_{self.name}.jpg", caption=caption)
            return True
        except Exception as e:
            _logger.error("Failed to send discount table for session %s: %s", self.name, e)
            return False

    def action_pos_session_close(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """Override to send Telegram notification after closing."""
        # Call original method
        result = super().action_pos_session_close(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs
        )

        # Send the Telegram notification only once the close is committed.
        # Later steps of the closing (e.g. pos_hr's "Closed Register" message)
        # can still fail and roll the whole close back; sending here directly
        # announced closes that never happened.
        closed_ids = self.filtered(lambda s: s.state == 'closed').ids
        if closed_ids:
            dbname, uid, context = self.env.cr.dbname, self.env.uid, dict(self.env.context)

            def send_after_commit():
                try:
                    with self.env.registry.cursor() as cr:
                        env = api.Environment(cr, uid, context)
                        for session in env['pos.session'].browse(closed_ids):
                            session._send_telegram_session_summary()
                except Exception:
                    _logger.exception("Telegram summary after closing %s failed", dbname)

            self.env.cr.postcommit.add(send_after_commit)

        return result
