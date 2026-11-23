# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDlAppCards(TransactionCase):
    """The session closing, cancelled / edited orders arrive in the app as organized cards, not Telegram text."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.sudo().write({'telegram_enabled': False, 'telegram_send_on_order_cancel': True,
                                  'telegram_pos_close_send_pdf': True})
        cls.manager = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'DLC Manager', 'login': 'dlc_manager', 'groups_id': [(6, 0, cls.env.ref('base.group_user').ids)]})
        for code in ('pos_session', 'pos_order_alert'):
            cls.env['donialink.app.kind']._get(code).write({'recipient_ids': [(6, 0, cls.manager.ids)], 'recipient_group_ids': [(5, 0, 0)], 'role_ids': [(5, 0, 0)]})
        cash = cls.env['account.journal'].create({'name': 'DLC Cash', 'code': 'DLCC', 'type': 'cash',
                                                   'company_id': cls.company.id})
        method = cls.env['pos.payment.method'].create({'name': 'DLC Cash', 'journal_id': cash.id, 'is_cash_count': True})
        cls.config = cls.env['pos.config'].create({'name': 'DLC Shop', 'payment_method_ids': [(6, 0, method.ids)]})
        cls.session = cls.env['pos.session'].create({'config_id': cls.config.id, 'user_id': cls.env.uid})
        cls.product = cls.env['product.product'].create({'name': 'DLC Burger', 'list_price': 10000,
                                                         'available_in_pos': True, 'taxes_id': [(5, 0, 0)]})
        cls.cash_journal = cash

    def _order(self, qty=2, discount=0.0, state='paid'):
        total = 10000 * qty * (1 - discount / 100)
        order = self.env['pos.order'].create({
            'session_id': self.session.id, 'company_id': self.company.id, 'amount_tax': 0, 'amount_total': total,
            'amount_paid': total if state == 'paid' else 0, 'amount_return': 0,
            'lines': [(0, 0, {'product_id': self.product.id, 'qty': qty, 'price_unit': 10000, 'discount': discount,
                              'price_subtotal': total, 'price_subtotal_incl': total, 'full_product_name': 'DLC Burger'})],
        })
        if state != 'draft':
            order.state = state
        return order

    def test_session_card(self):
        self._order(qty=2, discount=50)                    # a discount of 10,000
        self._order(qty=1)
        self._order(qty=3, state='cancel')                 # a cancelled order
        self.env['account.bank.statement.line'].create({
            'journal_id': self.cash_journal.id, 'amount': -5000, 'pos_session_id': self.session.id,
            'payment_ref': '%s-out-Gas cylinder' % self.session.name})
        Session = type(self.session)
        with patch.object(Session, '_session_pdf_content', return_value=b'%PDF-1.4 sales'):
            self.session._send_session_report()
        message = self.env['donialink.app.message'].search([('kind_code', '=', 'pos_session'), ('user_id', '=', self.manager.id)])
        self.assertEqual(len(message), 1)
        self.assertEqual(message.title, 'إغلاق الجلسة: DLC Shop — %s' % self.session.name)
        body = str(message.body)
        for piece in ('dl-rep-kpis', 'dl-rep-table', 'حركات الجلسة', 'جدول الخصومات', 'Gas cylinder',
                      'طلب ملغى', 'التقارير', 'الصندوق'):
            self.assertIn(piece, body, piece)
        self.assertNotIn('<br><br>', body, 'not the Telegram text')
        self.assertTrue(message.preview.startswith('المبيعات'), 'the notification shows the key figures first')
        self.assertEqual(message.attachment_id.name, 'POS_Sales_%s.pdf' % self.session.name)

    def test_cancelled_order_card(self):
        order = self._order(qty=3, state='cancel')
        order._schedule_telegram_cancel_messages(order)
        messages = self.env['donialink.app.message'].search([('kind_code', '=', 'pos_order_alert'), ('user_id', '=', self.manager.id)])
        self.assertEqual(len(messages), 1, 'one organized card, not a second text copy')
        self.assertTrue(messages.title.startswith('🚫 طلب ملغى #'))
        self.assertIn('dl-rep-table', str(messages.body))
        self.assertIn('DLC Burger', str(messages.body))
        self.assertEqual(messages.url, '/odoo/pos.order/%s' % order.id)

    def test_edited_order_card(self):
        if 'pos.order.edit.log' not in self.env:
            self.skipTest('dev_pos_access_rights is not installed')
        order = self._order(qty=3, state='draft')
        logs = self.env['pos.order.edit.log'].create({
            'order_id': order.id, 'product_id': self.product.id, 'product_name': 'DLC Burger', 'qty_before': 3,
            'qty_after': 1, 'amount': 20000, 'reason': 'customer changed mind', 'edited_by': 'Ali'})
        order._telegram_order_edit_alert(logs)
        messages = self.env['donialink.app.message'].search([('kind_code', '=', 'pos_order_alert'), ('user_id', '=', self.manager.id)])
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages.title.startswith('✂️ تعديل طلب #'))
        self.assertIn('customer changed mind', str(messages.body))
        card = self.session._dl_app_session_card()[1]
        self.assertIn('تعديل طلب', card, 'the edit is a movement of the session')

    def test_printer_kind_recipients(self):
        printer = self.env.ref('telegram_reports.kind_printer_alert')
        printer.recipient_ids = False
        self.env['donialink.app.kind']._dl_printer_kind_recipients()
        self.assertIn(self.manager, printer.recipient_ids, 'the people who receive the cancelled orders')
