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
        ('pnl', 'Profit & Loss Summary'),
        ('custom', 'Custom Summary'),
    ], string='Summary Type', default='pos', required=True)

    # P&L Options
    pnl_period = fields.Selection([
        ('current_month', 'Current Month'),
        ('last_month', 'Last Month'),
        ('current_year', 'Current Year'),
    ], string='P&L Period', default='current_month')

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

        # Check if Sales module is installed
        if 'sale.order' not in self.env:
            return "⚠️ Sales module not installed\nوحدة المبيعات غير مثبتة"

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

        # Check if Accounting module is installed
        if 'account.move' not in self.env:
            return "⚠️ Accounting module not installed\nوحدة المحاسبة غير مثبتة"

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

    def _get_pnl_summary(self):
        """Generate Profit & Loss summary."""
        self.ensure_one()

        # Check if Accounting module is installed
        if 'account.move.line' not in self.env:
            return "⚠️ Accounting module not installed\nوحدة المحاسبة غير مثبتة"

        # Determine date range based on period
        today = fields.Date.today()
        if self.pnl_period == 'current_month':
            date_from = today.replace(day=1)
            date_to = today
            period_name = today.strftime('%B %Y')
            period_name_ar = f"شهر {today.month}/{today.year}"
        elif self.pnl_period == 'last_month':
            first_of_month = today.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            date_from = last_month_end.replace(day=1)
            date_to = last_month_end
            period_name = last_month_end.strftime('%B %Y')
            period_name_ar = f"شهر {last_month_end.month}/{last_month_end.year}"
        else:  # current_year
            date_from = today.replace(month=1, day=1)
            date_to = today
            period_name = str(today.year)
            period_name_ar = f"سنة {today.year}"

        company = self.env.company
        currency = company.currency_id

        # Get income accounts (Odoo 18 syntax with company context)
        income_accounts = self.env['account.account'].with_company(company).search([
            ('account_type', '=', 'income'),
        ])

        # Get expense accounts (Odoo 18 syntax with company context)
        expense_accounts = self.env['account.account'].with_company(company).search([
            ('account_type', '=', 'expense'),
        ])

        # Calculate income (credit - debit for income accounts)
        income_lines = self.env['account.move.line'].search([
            ('account_id', 'in', income_accounts.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ])
        total_income = sum(income_lines.mapped('credit')) - sum(income_lines.mapped('debit'))

        # Calculate expenses (debit - credit for expense accounts)
        expense_lines = self.env['account.move.line'].search([
            ('account_id', 'in', expense_accounts.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ])
        total_expenses = sum(expense_lines.mapped('debit')) - sum(expense_lines.mapped('credit'))

        # Calculate profit/loss
        net_profit = total_income - total_expenses

        # Build message
        msg = f"📊 <b>تقرير الأرباح والخسائر</b>\n"
        msg += f"📅 {period_name_ar}\n"
        msg += f"🏢 {company.name}\n"
        msg += f"{'─' * 28}\n\n"

        msg += f"💵 <b>الإيرادات:</b> {total_income:,.2f} {currency.symbol}\n"
        msg += f"💸 <b>المصروفات:</b> {total_expenses:,.2f} {currency.symbol}\n"
        msg += f"{'─' * 28}\n"

        if net_profit >= 0:
            msg += f"✅ <b>صافي الربح:</b> {net_profit:,.2f} {currency.symbol}\n"
        else:
            msg += f"❌ <b>صافي الخسارة:</b> {abs(net_profit):,.2f} {currency.symbol}\n"

        # Profit margin
        if total_income > 0:
            margin = (net_profit / total_income) * 100
            msg += f"📈 <b>هامش الربح:</b> {margin:.1f}%\n"

        # Top expense categories
        msg += f"\n💰 <b>أعلى المصروفات:</b>\n"
        expense_by_account = {}
        for line in expense_lines:
            acc_name = line.account_id.name
            expense_by_account[acc_name] = expense_by_account.get(acc_name, 0) + (line.debit - line.credit)

        top_expenses = sorted(expense_by_account.items(), key=lambda x: -x[1])[:5]
        for i, (account, amount) in enumerate(top_expenses, 1):
            if amount > 0:
                msg += f"  {i}. {account}: {amount:,.2f} {currency.symbol}\n"

        # Top income sources
        msg += f"\n💵 <b>أعلى الإيرادات:</b>\n"
        income_by_account = {}
        for line in income_lines:
            acc_name = line.account_id.name
            income_by_account[acc_name] = income_by_account.get(acc_name, 0) + (line.credit - line.debit)

        top_income = sorted(income_by_account.items(), key=lambda x: -x[1])[:5]
        for i, (account, amount) in enumerate(top_income, 1):
            if amount > 0:
                msg += f"  {i}. {account}: {amount:,.2f} {currency.symbol}\n"

        msg += f"\n{'─' * 28}\n"
        msg += f"📆 من: {date_from.strftime('%Y-%m-%d')}\n"
        msg += f"📆 إلى: {date_to.strftime('%Y-%m-%d')}\n"
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
        elif self.summary_type == 'pnl':
            message = self._get_pnl_summary()
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
