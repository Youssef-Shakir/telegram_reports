# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDlAppAlerts(TransactionCase):
    """Every alert lands in the DoniaLink App; Telegram is an optional copy through the company's own bot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.sudo().write({'telegram_enabled': True, 'telegram_bot_token': '123:test-token',
                                  'telegram_default_chat_id': '-100111', 'telegram_chat_pos': False,
                                  'telegram_chat_summary': False, 'telegram_chat_reports': False,
                                  'telegram_chat_order_now': False})
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.manager = Users.create({'name': 'DLT Manager', 'login': 'dlt_manager',
                                    'groups_id': [(6, 0, cls.env.ref('base.group_user').ids)]})
        cls.Kind = cls.env['donialink.app.kind']
        cls.Message = cls.env['donialink.app.message']
        for code in ('daily_summary', 'pos_session', 'pos_order_alert'):
            cls.Kind._get(code).write({'recipient_ids': [(6, 0, cls.manager.ids)], 'recipient_group_ids': [(5, 0, 0)], 'role_ids': [(5, 0, 0)]})

    def setUp(self):
        super().setUp()
        # Telegram itself: the own bot's API calls
        patcher = patch.object(type(self.env['telegram.service']), '_make_request',
                               return_value={'ok': True, 'result': {'message_id': 7}})
        self.telegram = patcher.start()
        self.addCleanup(patcher.stop)

    def _messages(self, kind):
        return self.Message.search([('kind_code', '=', kind), ('user_id', '=', self.manager.id)])

    def _service(self, kind):
        return self.env['telegram.service'].with_company(self.company).with_context(telegram_kind=kind)

    def test_kinds_exist(self):
        codes = set(self.Kind.search([]).mapped('code'))
        for code in ('pos_session', 'pos_order_alert', 'daily_summary', 'finance_summary', 'scheduled_report',
                     'order_now'):
            self.assertIn(code, codes)

    def test_alert_in_app_and_telegram(self):
        self._service('daily_summary').send_message('📊 <b>Sales today</b>\nTotal: 1,000')
        message = self._messages('daily_summary')
        self.assertEqual(message.user_id, self.manager)
        self.assertEqual(message.title, '📊 Sales today')
        self.assertIn('<br>', message.body, 'line breaks kept in the app')
        self.assertEqual(self.telegram.call_count, 1, 'Telegram also gets it')
        self.assertEqual(self.telegram.call_args.kwargs['data']['chat_id'], '-100111')

    def test_group_per_kind(self):
        self.company.sudo().telegram_chat_summary = '-100222'
        self._service('daily_summary').send_message('<b>x</b>')
        self.assertEqual(self.telegram.call_args.kwargs['data']['chat_id'], '-100222')
        self._service('scheduled_report').send_message('<b>y</b>')
        self.assertEqual(self.telegram.call_args.kwargs['data']['chat_id'], '-100111', 'empty: the main group')

    def test_telegram_off(self):
        self.company.sudo().telegram_enabled = False
        self.assertTrue(self._service('daily_summary').send_message('<b>Only the app</b>'))
        self._service('daily_summary').send_document(b'%PDF-1.4', 'summary.pdf', caption='Monthly')
        self.assertEqual(len(self._messages('daily_summary')), 2)
        self.assertEqual(self._messages('daily_summary').attachment_id.name, 'summary.pdf')
        self.telegram.assert_not_called()
        # on, but no token: nothing goes to Telegram either
        self.company.sudo().write({'telegram_enabled': True, 'telegram_bot_token': False})
        self._service('daily_summary').send_message('<b>again</b>')
        self.telegram.assert_not_called()

    def test_off_by_default(self):
        company = self.env['res.company'].create({'name': 'DLT New Co'})
        self.assertFalse(company.telegram_enabled)
        self.assertTrue(company._telegram_off())

    def test_test_message_is_not_an_alert(self):
        self._service('test').send_message('hi')
        self.assertFalse(self.Message.search([('title', '=', 'hi')]))

    def test_archived_kind_sends_nothing(self):
        self.Kind._get('daily_summary').active = False
        self._service('daily_summary').send_message('<b>x</b>')
        self.assertFalse(self._messages('daily_summary'))

    def test_session_report_is_one_app_message(self):
        session = self.env['pos.session'].search([], limit=1)
        if not session:
            self.skipTest('no POS session in this database')
        Session = type(session)
        with patch.object(Session, '_prepare_session_summary_message', return_value='🏪 <b>Shop</b>\nSales 10'), \
                patch.object(Session, '_session_pdf_content', return_value=b'%PDF-1.4 sales'), \
                patch.object(Session, '_send_discount_table', return_value=True), \
                patch.object(Session, '_send_session_pdf_report', return_value=True):
            session._send_session_report()
        message = self._messages('pos_session')
        self.assertEqual(len(message), 1)
        self.assertEqual(message.attachment_id.name, 'POS_Sales_%s.pdf' % session.name)
        self.assertEqual(message.url, '/odoo/pos.session/%s' % session.id)
        self.assertEqual(self.telegram.call_count, 1, 'the summary on Telegram, not a second app message')

        self.company.sudo().telegram_enabled = False
        self.telegram.reset_mock()
        with patch.object(Session, '_prepare_session_summary_message', return_value='again'), \
                patch.object(Session, '_session_pdf_content', return_value=None):
            session._send_session_report()
        self.assertEqual(len(self._messages('pos_session')), 2)
        self.telegram.assert_not_called()

    def test_order_alerts(self):
        self.company.sudo().telegram_enabled = False
        self.env['pos.order']._telegram_send_order_alerts(self.company, ['🚫 <b>Order cancelled</b> #0042'])
        message = self._messages('pos_order_alert')
        self.assertEqual((message.title, message.user_id), ('🚫 Order cancelled #0042', self.manager))

    def test_no_platform_left(self):
        """Nothing in Telegram Reports talks to the DoniaLink Platform any more."""
        Service = type(self.env['telegram.service'])
        for name in ('donialink_post', '_via_donialink', '_send_through_donialink'):
            self.assertFalse(hasattr(Service, name), name)
        self.assertNotIn('telegram_delivery', self.env['res.company']._fields)
