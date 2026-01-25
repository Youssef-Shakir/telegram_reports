# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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

    def action_pos_session_close(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """Override to send Telegram notification after closing."""
        # Call original method
        result = super().action_pos_session_close(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs
        )

        # Send Telegram notification for closed sessions
        for session in self:
            if session.state == 'closed':
                session._send_telegram_session_summary()

        return result
