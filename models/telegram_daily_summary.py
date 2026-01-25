# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TelegramDailySummary(models.Model):
    """Daily sales summary for Telegram."""
    _name = 'telegram.daily.summary'
    _description = 'Telegram Daily Summary'
    _order = 'sequence, name'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Sequence', default=10)

    # Summary type
    summary_type = fields.Selection([
        ('pos', 'POS Sales Summary'),
        ('sales', 'Sales Orders Summary'),
        ('invoices', 'Invoices Summary'),
        ('custom', 'Custom Summary'),
    ], string='Summary Type', default='pos', required=True)

    # Schedule
    schedule_time = fields.Float(
        'Send Time',
        default=21.0,
        help='Time to send daily summary (24-hour format)'
    )

    # Telegram
    chat_id = fields.Char('Chat ID', help='Leave empty for default')

    # Options
    include_top_products = fields.Boolean('Include Top Products', default=True)
    top_products_count = fields.Integer('Number of Top Products', default=5)
    include_payment_summary = fields.Boolean('Include Payment Summary', default=True)

    # Tracking
    last_sent = fields.Datetime('Last Sent', readonly=True)

    def _get_pos_summary(self, date=None):
        """Generate POS sales summary for a specific date."""
        self.ensure_one()
        date = date or fields.Date.today()

        # Check if POS module is installed
        if 'pos.order' not in self.env:
            return "⚠️ POS module not installed"

        # Get POS orders for today
        orders = self.env['pos.order'].search([
            ('date_order', '>=', datetime.combine(date, datetime.min.time())),
            ('date_order', '<=', datetime.combine(date, datetime.max.time())),
            ('state', 'in', ['paid', 'done', 'invoiced']),
        ])

        if not orders:
            return self._format_no_sales_message(date)

        # Calculate totals
        total_sales = sum(orders.mapped('amount_total'))
        total_orders = len(orders)
        currency = orders[0].currency_id if orders else self.env.company.currency_id

        # Build message
        msg = f"📊 <b>تقرير مبيعات اليوم</b>\n"
        msg += f"📅 {date.strftime('%Y-%m-%d')}\n"
        msg += f"{'─' * 25}\n\n"

        msg += f"💰 <b>إجمالي المبيعات:</b> {total_sales:,.2f} {currency.symbol}\n"
        msg += f"🧾 <b>عدد الطلبات:</b> {total_orders}\n"

        if total_orders > 0:
            avg_order = total_sales / total_orders
            msg += f"📈 <b>متوسط الطلب:</b> {avg_order:,.2f} {currency.symbol}\n"

        # Payment summary
        if self.include_payment_summary:
            msg += f"\n💳 <b>طرق الدفع:</b>\n"
            payments = {}
            for order in orders:
                for payment in order.payment_ids:
                    method = payment.payment_method_id.name
                    payments[method] = payments.get(method, 0) + payment.amount

            for method, amount in sorted(payments.items(), key=lambda x: -x[1]):
                msg += f"  • {method}: {amount:,.2f} {currency.symbol}\n"

        # Top products
        if self.include_top_products:
            msg += f"\n🏆 <b>المنتجات الأكثر مبيعاً:</b>\n"
            product_sales = {}
            for order in orders:
                for line in order.lines:
                    product = line.product_id.name
                    product_sales[product] = product_sales.get(product, 0) + line.qty

            top_products = sorted(product_sales.items(), key=lambda x: -x[1])[:self.top_products_count]
            for i, (product, qty) in enumerate(top_products, 1):
                msg += f"  {i}. {product}: {qty:,.0f}\n"

        # Sessions info
        sessions = orders.mapped('session_id')
        if sessions:
            msg += f"\n🏪 <b>الجلسات:</b> {len(sessions)}\n"
            for session in sessions:
                msg += f"  • {session.name}\n"

        msg += f"\n{'─' * 25}\n"
        msg += f"⏰ {datetime.now().strftime('%H:%M')}"

        return msg

    def _get_sales_summary(self, date=None):
        """Generate Sales Orders summary."""
        self.ensure_one()
        date = date or fields.Date.today()

        orders = self.env['sale.order'].search([
            ('date_order', '>=', datetime.combine(date, datetime.min.time())),
            ('date_order', '<=', datetime.combine(date, datetime.max.time())),
            ('state', 'in', ['sale', 'done']),
        ])

        if not orders:
            return self._format_no_sales_message(date)

        total_sales = sum(orders.mapped('amount_total'))
        total_orders = len(orders)
        currency = orders[0].currency_id if orders else self.env.company.currency_id

        msg = f"📊 <b>تقرير طلبات البيع</b>\n"
        msg += f"📅 {date.strftime('%Y-%m-%d')}\n"
        msg += f"{'─' * 25}\n\n"

        msg += f"💰 <b>إجمالي المبيعات:</b> {total_sales:,.2f} {currency.symbol}\n"
        msg += f"🧾 <b>عدد الطلبات:</b> {total_orders}\n"

        # Top products
        if self.include_top_products:
            msg += f"\n🏆 <b>المنتجات الأكثر مبيعاً:</b>\n"
            product_sales = {}
            for order in orders:
                for line in order.order_line:
                    if line.product_id:
                        product = line.product_id.name
                        product_sales[product] = product_sales.get(product, 0) + line.product_uom_qty

            top_products = sorted(product_sales.items(), key=lambda x: -x[1])[:self.top_products_count]
            for i, (product, qty) in enumerate(top_products, 1):
                msg += f"  {i}. {product}: {qty:,.0f}\n"

        msg += f"\n{'─' * 25}\n"
        msg += f"⏰ {datetime.now().strftime('%H:%M')}"

        return msg

    def _get_invoices_summary(self, date=None):
        """Generate Invoices summary."""
        self.ensure_one()
        date = date or fields.Date.today()

        invoices = self.env['account.move'].search([
            ('invoice_date', '=', date),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ])

        if not invoices:
            return self._format_no_sales_message(date, "فواتير")

        total = sum(invoices.mapped('amount_total'))
        currency = invoices[0].currency_id if invoices else self.env.company.currency_id

        msg = f"📊 <b>تقرير الفواتير</b>\n"
        msg += f"📅 {date.strftime('%Y-%m-%d')}\n"
        msg += f"{'─' * 25}\n\n"

        msg += f"💰 <b>إجمالي الفواتير:</b> {total:,.2f} {currency.symbol}\n"
        msg += f"🧾 <b>عدد الفواتير:</b> {len(invoices)}\n"

        msg += f"\n{'─' * 25}\n"
        msg += f"⏰ {datetime.now().strftime('%H:%M')}"

        return msg

    def _format_no_sales_message(self, date, type_name="مبيعات"):
        """Format message when no sales found."""
        msg = f"📊 <b>تقرير {type_name} اليوم</b>\n"
        msg += f"📅 {date.strftime('%Y-%m-%d')}\n"
        msg += f"{'─' * 25}\n\n"
        msg += f"❌ لا توجد {type_name} لهذا اليوم\n"
        msg += f"\n{'─' * 25}\n"
        msg += f"⏰ {datetime.now().strftime('%H:%M')}"
        return msg

    def action_send_now(self):
        """Send summary now."""
        self.ensure_one()

        if self.summary_type == 'pos':
            message = self._get_pos_summary()
        elif self.summary_type == 'sales':
            message = self._get_sales_summary()
        elif self.summary_type == 'invoices':
            message = self._get_invoices_summary()
        else:
            raise UserError(_('Custom summary not implemented yet'))

        telegram = self.env['telegram.service']
        telegram.send_message(message, chat_id=self.chat_id or None)

        self.last_sent = fields.Datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Summary sent to Telegram!'),
                'type': 'success',
            }
        }

    @api.model
    def _cron_send_daily_summaries(self):
        """Cron job to send daily summaries."""
        now = fields.Datetime.now()
        current_hour = now.hour + now.minute / 60

        summaries = self.search([
            ('active', '=', True),
        ])

        for summary in summaries:
            # Check if it's time to send (within 15-minute window)
            if abs(summary.schedule_time - current_hour) <= 0.25:
                # Check if already sent today
                if summary.last_sent:
                    last_sent_date = fields.Datetime.context_timestamp(summary, summary.last_sent).date()
                    if last_sent_date == now.date():
                        continue

                try:
                    summary.action_send_now()
                    _logger.info("Sent daily summary: %s", summary.name)
                except Exception as e:
                    _logger.error("Failed to send summary %s: %s", summary.name, str(e))

        return True
