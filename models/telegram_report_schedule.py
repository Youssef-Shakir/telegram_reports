# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TelegramReportSchedule(models.Model):
    """Scheduled Telegram report configuration."""
    _name = 'telegram.report.schedule'
    _description = 'Telegram Report Schedule'
    _order = 'sequence, name'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Sequence', default=10)

    # Report configuration
    report_id = fields.Many2one(
        'ir.actions.report',
        string='Report',
        required=True,
        domain="[('report_type', 'in', ['qweb-pdf', 'qweb-html'])]",
        help='Select the report to send'
    )

    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        related='report_id.model_id',
        store=True,
        readonly=True
    )

    # Filter configuration
    domain = fields.Char(
        'Filter Domain',
        default='[]',
        help='Domain filter to select records. Use [] for all records. '
             'Example: [(\'state\', \'=\', \'posted\')]'
    )

    limit_records = fields.Integer(
        'Limit Records',
        default=0,
        help='Maximum number of records to include. 0 for no limit.'
    )

    # Telegram configuration
    chat_id = fields.Char(
        'Chat ID',
        help='Specific chat ID for this report. Leave empty to use default.'
    )

    caption_template = fields.Text(
        'Caption Template',
        default='📊 {report_name}\n📅 {date}',
        help='Caption template. Available variables: {report_name}, {date}, {record_count}'
    )

    # Schedule configuration
    schedule_type = fields.Selection([
        ('manual', 'Manual Only'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string='Schedule', default='manual', required=True)

    schedule_time = fields.Float(
        'Send Time',
        default=9.0,
        help='Time to send the report (24-hour format, e.g., 9.5 for 9:30 AM)'
    )

    schedule_day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', default='0')

    schedule_day_of_month = fields.Integer(
        'Day of Month',
        default=1,
        help='Day of month to send (1-28). Use 1 for first day.'
    )

    # Tracking
    last_sent = fields.Datetime('Last Sent', readonly=True)
    next_scheduled = fields.Datetime('Next Scheduled', compute='_compute_next_scheduled', store=True)
    send_count = fields.Integer('Send Count', default=0, readonly=True)

    @api.depends('schedule_type', 'schedule_time', 'schedule_day_of_week', 'schedule_day_of_month', 'last_sent')
    def _compute_next_scheduled(self):
        """Compute next scheduled send time."""
        for record in self:
            if record.schedule_type == 'manual':
                record.next_scheduled = False
                continue

            now = fields.Datetime.now()
            hour = int(record.schedule_time)
            minute = int((record.schedule_time % 1) * 60)

            if record.schedule_type == 'daily':
                next_send = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_send <= now:
                    next_send += timedelta(days=1)

            elif record.schedule_type == 'weekly':
                days_ahead = int(record.schedule_day_of_week) - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                next_send = now + timedelta(days=days_ahead)
                next_send = next_send.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_send <= now:
                    next_send += timedelta(days=7)

            elif record.schedule_type == 'monthly':
                day = min(record.schedule_day_of_month, 28)
                next_send = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                if next_send <= now:
                    # Move to next month
                    if now.month == 12:
                        next_send = next_send.replace(year=now.year + 1, month=1)
                    else:
                        next_send = next_send.replace(month=now.month + 1)
            else:
                next_send = False

            record.next_scheduled = next_send

    def _get_records(self):
        """Get records to include in report based on domain."""
        self.ensure_one()

        try:
            domain = eval(self.domain or '[]')
        except Exception as e:
            _logger.error("Invalid domain for schedule %s: %s", self.name, str(e))
            domain = []

        model = self.env[self.report_id.model]
        records = model.search(domain, limit=self.limit_records or None)

        return records

    def _get_caption(self, record_count=0):
        """Generate caption from template."""
        self.ensure_one()

        template = self.caption_template or '{report_name}'
        return template.format(
            report_name=self.report_id.name,
            date=fields.Date.today().strftime('%Y-%m-%d'),
            record_count=record_count,
        )

    def action_send_now(self):
        """Manually send the report now."""
        self.ensure_one()

        if not self.report_id:
            raise UserError(_('No report selected for this schedule.'))

        records = self._get_records()
        if not records:
            raise UserError(_('No records found matching the filter criteria.'))

        caption = self._get_caption(len(records))
        chat_id = self.chat_id or None

        telegram = self.env['telegram.service']
        try:
            success = telegram.send_pdf_report(
                self.report_id,
                records.ids,
                chat_id=chat_id,
                caption=caption,
                filename=f"{self.name}.pdf"
            )
        except Exception as e:
            raise UserError(_('Failed to send report: %s') % str(e))

        if success:
            self.write({
                'last_sent': fields.Datetime.now(),
                'send_count': self.send_count + 1,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Report sent successfully to Telegram!'),
                    'type': 'success',
                }
            }
        else:
            raise UserError(_('Failed to send report. Check Telegram configuration.'))

    @api.model
    def _cron_send_scheduled_reports(self):
        """Cron job to send scheduled reports."""
        now = fields.Datetime.now()

        # Find reports due to be sent
        schedules = self.search([
            ('active', '=', True),
            ('schedule_type', '!=', 'manual'),
            ('next_scheduled', '<=', now),
        ])

        for schedule in schedules:
            try:
                records = schedule._get_records()
                if not records:
                    _logger.info("No records for scheduled report: %s", schedule.name)
                    continue

                caption = schedule._get_caption(len(records))
                chat_id = schedule.chat_id or None

                telegram = self.env['telegram.service']
                success = telegram.send_pdf_report(
                    schedule.report_id,
                    records.ids,
                    chat_id=chat_id,
                    caption=caption,
                    filename=f"{schedule.name}.pdf"
                )

                if success:
                    schedule.write({
                        'last_sent': now,
                        'send_count': schedule.send_count + 1,
                    })
                    _logger.info("Sent scheduled report: %s", schedule.name)
                else:
                    _logger.error("Failed to send scheduled report: %s", schedule.name)

            except Exception as e:
                _logger.error("Error sending scheduled report %s: %s", schedule.name, str(e))

        return True
