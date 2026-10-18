# -*- coding: utf-8 -*-
import logging
import requests
import base64

from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramService(models.AbstractModel):
    """Service model for Telegram API interactions."""
    _name = 'telegram.service'
    _description = 'Telegram Service'

    def _get_bot_token(self):
        """Get the configured bot token."""
        return self.env['ir.config_parameter'].sudo().get_param('telegram_reports.bot_token', '')

    def _get_default_chat_id(self):
        """Get the default chat ID."""
        return self.env['ir.config_parameter'].sudo().get_param('telegram_reports.default_chat_id', '')

    def _make_request(self, method, data=None, files=None):
        """Make a request to Telegram API."""
        token = self._get_bot_token()
        if not token:
            _logger.error("Telegram bot token not configured")
            raise UserError(_('Telegram bot token not configured. Go to Settings to configure it.'))

        url = TELEGRAM_API_URL.format(token=token, method=method)

        try:
            if files:
                response = requests.post(url, data=data, files=files, timeout=30)
            else:
                response = requests.post(url, data=data, timeout=30)

            result = response.json()

            if not result.get('ok'):
                error_msg = result.get('description', 'Unknown error')
                _logger.error("Telegram API error: %s", error_msg)
                raise UserError(_('Telegram API error: %s') % error_msg)

            return result

        except requests.exceptions.RequestException as e:
            _logger.error("Telegram request failed: %s", str(e))
            raise UserError(_('Telegram connection failed: %s') % str(e))

    def send_message(self, text, chat_id=None, parse_mode='HTML'):
        """Send a text message to Telegram."""
        chat_id = chat_id or self._get_default_chat_id()
        if not chat_id:
            raise UserError(_('No chat ID configured. Go to Settings to configure it.'))

        result = None
        for chunk in self._split_message(text):
            result = self._make_request('sendMessage', data={
                'chat_id': chat_id,
                'text': chunk,
                'parse_mode': parse_mode,
            })
        return bool(result)

    # Telegram rejects messages over 4096 characters; keep a margin.
    MESSAGE_LIMIT = 4000

    def _split_message(self, text):
        """Split a long message at line breaks into parts Telegram accepts.
        Our HTML tags never span lines, so a part never cuts a tag in two."""
        if len(text) <= self.MESSAGE_LIMIT:
            return [text]
        parts, current = [], ''
        for line in text.split('\n'):
            while len(line) > self.MESSAGE_LIMIT:   # a single huge line
                if current:
                    parts.append(current)
                    current = ''
                parts.append(line[:self.MESSAGE_LIMIT])
                line = line[self.MESSAGE_LIMIT:]
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > self.MESSAGE_LIMIT:
                parts.append(current)
                current = line
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    def send_document(self, document, filename, chat_id=None, caption=None):
        """Send a document/file to Telegram."""
        chat_id = chat_id or self._get_default_chat_id()
        if not chat_id:
            raise UserError(_('No chat ID configured. Go to Settings to configure it.'))

        # Handle base64 encoded content
        if isinstance(document, str):
            document = base64.b64decode(document)

        data = {
            'chat_id': chat_id,
        }
        if caption:
            data['caption'] = caption
            data['parse_mode'] = 'HTML'

        files = {
            'document': (filename, document),
        }

        result = self._make_request('sendDocument', data=data, files=files)
        return bool(result)

    def send_photo(self, image, filename, chat_id=None, caption=None):
        """Send an image (bytes) as a Telegram photo."""
        chat_id = chat_id or self._get_default_chat_id()
        if not chat_id:
            raise UserError(_('No chat ID configured. Go to Settings to configure it.'))
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
            data['parse_mode'] = 'HTML'
        result = self._make_request('sendPhoto', data=data, files={'photo': (filename, image)})
        return bool(result)

    def send_pdf_report(self, report_ref, record_ids, chat_id=None, caption=None, filename=None):
        """Send an Odoo report as PDF to Telegram."""
        # Get report action
        if isinstance(report_ref, str):
            report = self.env.ref(report_ref, raise_if_not_found=False)
            if not report:
                raise UserError(_('Report not found: %s') % report_ref)
        else:
            report = report_ref

        if not record_ids:
            raise UserError(_('No records to include in the report.'))

        # Generate PDF
        try:
            # _render_qweb_pdf expects (report_ref, res_ids) where report_ref can be the report record
            pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report.report_name,  # Use report_name as reference
                record_ids
            )
            _logger.info("PDF generated successfully for report: %s, records: %s", report.report_name, record_ids)
        except Exception as e:
            _logger.error("Failed to generate PDF for report %s: %s", report.report_name if hasattr(report, 'report_name') else report, str(e))
            raise UserError(_('Failed to generate PDF: %s') % str(e))

        # Generate filename
        if not filename:
            filename = f"{report.name}_{record_ids[0] if record_ids else 'report'}.pdf"
        elif not filename.endswith('.pdf'):
            filename += '.pdf'

        return self.send_document(pdf_content, filename, chat_id=chat_id, caption=caption)

    def send_pos_sale_details_report(self, session, data, chat_id=None, caption=None, filename=None):
        """Send POS sale details report as PDF to Telegram.

        This report is data-driven (uses date range and config IDs) rather than record-driven.
        """
        report = self.env.ref('point_of_sale.sale_details_report', raise_if_not_found=False)
        if not report:
            raise UserError(_('POS Sale Details report not found'))

        # Generate PDF with data
        try:
            pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report.report_name,
                [],  # Empty record IDs - this report uses data dict
                data=data
            )
            _logger.info("POS Sale Details PDF generated successfully for session: %s", session.name)
        except Exception as e:
            _logger.error("Failed to generate POS Sale Details PDF: %s", str(e))
            raise UserError(_('Failed to generate PDF: %s') % str(e))

        # Generate filename
        if not filename:
            filename = f"POS_Sales_{session.name}.pdf"
        elif not filename.endswith('.pdf'):
            filename += '.pdf'

        return self.send_document(pdf_content, filename, chat_id=chat_id, caption=caption)

    def send_financial_report(self, report_ref, data, chat_id=None, caption=None, filename=None):
        """Send financial/accounting report as PDF to Telegram.

        Financial reports typically require date ranges and other parameters
        passed via the data dict rather than record IDs.
        """
        # Get report action
        if isinstance(report_ref, str):
            report = self.env.ref(report_ref, raise_if_not_found=False)
            if not report:
                raise UserError(_('Report not found: %s') % report_ref)
        else:
            report = report_ref

        _logger.info("Generating financial report: %s with data: %s", report.report_name, data)

        # Check if this is a base_accounting_kit financial report
        if report.report_name == 'base_accounting_kit.report_financial':
            return self._send_base_accounting_kit_report(report, data, chat_id, caption, filename)

        # Generate PDF with data for standard reports
        try:
            pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report.report_name,
                [],  # Empty record IDs - financial reports use data dict
                data=data
            )
            _logger.info("Financial report PDF generated successfully: %s", report.report_name)
        except Exception as e:
            _logger.error("Failed to generate financial report PDF %s: %s", report.report_name, str(e))
            raise UserError(_('Failed to generate PDF: %s') % str(e))

        # Generate filename
        if not filename:
            filename = f"{report.name}.pdf"
        elif not filename.endswith('.pdf'):
            filename += '.pdf'

        return self.send_document(pdf_content, filename, chat_id=chat_id, caption=caption)

    def _send_base_accounting_kit_report(self, report, data, chat_id=None, caption=None, filename=None):
        """Special handling for base_accounting_kit financial reports.

        These reports require creating a wizard record that computes
        report_lines and journal_items before generating the PDF.
        """
        # Check if financial.report model exists
        if 'financial.report' not in self.env:
            raise UserError(_('base_accounting_kit module not installed or financial.report model not found'))

        # Get account_report_id (P&L, Balance Sheet, etc.)
        # Default to first available financial report if not specified
        account_report = None
        if data.get('form', {}).get('account_report_id'):
            report_id = data['form']['account_report_id']
            if isinstance(report_id, (list, tuple)):
                report_id = report_id[0]
            account_report = self.env['account.financial.report'].browse(report_id)
        else:
            # Try to find a default financial report (e.g., Profit and Loss)
            account_report = self.env['account.financial.report'].search([
                ('name', 'ilike', 'Profit')
            ], limit=1)
            if not account_report:
                account_report = self.env['account.financial.report'].search([], limit=1)

        if not account_report:
            raise UserError(_('No financial report template found. Please configure account.financial.report'))

        _logger.info("Using account financial report: %s (ID: %s)", account_report.name, account_report.id)

        # Create the wizard record
        wizard_vals = {
            'date_from': data.get('date_from') or data.get('form', {}).get('date_from'),
            'date_to': data.get('date_to') or data.get('form', {}).get('date_to'),
            'account_report_id': account_report.id,
            'target_move': data.get('target_move', 'posted'),
            'view_format': data.get('view_format', 'vertical'),
            'debit_credit': data.get('debit_credit', True),
            'company_id': data.get('company_id') or self.env.company.id,
            'enable_filter': False,
        }

        wizard = self.env['financial.report'].create(wizard_vals)
        _logger.info("Created financial.report wizard: %s", wizard.id)

        # Build the data structure that the report template expects
        form_data = wizard.read([
            'date_from', 'enable_filter', 'debit_credit', 'date_to',
            'account_report_id', 'target_move', 'view_format', 'company_id'
        ])[0]

        report_data = {
            'ids': [],
            'model': 'ir.ui.menu',
            'form': form_data,
        }

        # Build context
        used_context = wizard._build_contexts(report_data)
        report_data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US'
        )

        # Get account lines and journal items (the key computation)
        report_lines = wizard.get_account_lines(report_data['form'])
        journal_items = wizard.find_journal_items(report_lines, report_data['form'])

        # Set levels for report lines
        def set_report_level(rec):
            level = 1
            if not rec['parent']:
                return level
            else:
                for line in report_lines:
                    key = 'a_id' if line['type'] == 'account' else 'id'
                    if line[key] == rec['parent']:
                        return level + set_report_level(line)
            return level

        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
            else:
                item['level'] = set_report_level(item)

        # Get currency
        currency = wizard._get_currency()

        # Complete the data structure
        report_data['currency'] = currency
        report_data['journal_items'] = journal_items
        report_data['report_lines'] = report_lines

        _logger.info("Generated %d report lines and %d journal items",
                    len(report_lines), len(journal_items))

        # Generate PDF
        try:
            pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report.report_name,
                [wizard.id],
                data=report_data
            )
            _logger.info("base_accounting_kit PDF generated successfully")
        except Exception as e:
            _logger.error("Failed to generate base_accounting_kit PDF: %s", str(e))
            raise UserError(_('Failed to generate PDF: %s') % str(e))

        # Generate filename
        if not filename:
            date_from = wizard_vals.get('date_from', '')
            date_to = wizard_vals.get('date_to', '')
            filename = f"{account_report.name}_{date_from}_{date_to}.pdf"
        elif not filename.endswith('.pdf'):
            filename += '.pdf'

        return self.send_document(pdf_content, filename, chat_id=chat_id, caption=caption)

    def test_connection(self, token=None, chat_id=None):
        """Test Telegram bot connection."""
        token = token or self._get_bot_token()
        chat_id = chat_id or self._get_default_chat_id()

        if not token:
            return {'success': False, 'message': _('Bot token not configured')}
        if not chat_id:
            return {'success': False, 'message': _('Chat ID not configured')}

        url = TELEGRAM_API_URL.format(token=token, method='getMe')
        try:
            response = requests.get(url, timeout=10)
            result = response.json()

            if not result.get('ok'):
                return {'success': False, 'message': _('Invalid bot token')}

            bot_name = result.get('result', {}).get('username', 'Unknown')

            # Try sending a test message
            test_data = {
                'chat_id': chat_id,
                'text': '✅ Odoo Telegram Reports connected successfully!\n\n'
                        'تم الاتصال بنجاح!',
            }
            send_url = TELEGRAM_API_URL.format(token=token, method='sendMessage')
            send_response = requests.post(send_url, data=test_data, timeout=10)
            send_result = send_response.json()

            if not send_result.get('ok'):
                error_desc = send_result.get('description', 'Unknown error')
                return {'success': False, 'message': _('Bot token valid but cannot send to chat: %s') % error_desc}

            return {
                'success': True,
                'message': _('Connected successfully! Bot: @%s') % bot_name
            }

        except requests.exceptions.RequestException as e:
            return {'success': False, 'message': _('Connection failed: %s') % str(e)}
