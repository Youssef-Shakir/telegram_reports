# -*- coding: utf-8 -*-
{
    'name': 'Telegram Reports',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Automatic report sending via Telegram',
    'description': """
Telegram Reports - تقارير تيليجرام
===================================

Automatically send Odoo reports to Telegram chats/groups.
إرسال تقارير أودو تلقائياً عبر تيليجرام.

Features | المميزات:
--------------------
* Configure Telegram Bot token and Chat ID
  إعداد توكن البوت ومعرف المحادثة

* Schedule automatic report sending (daily, weekly, monthly)
  جدولة إرسال التقارير تلقائياً (يومي، أسبوعي، شهري)

* Send any Odoo report as PDF
  إرسال أي تقرير أودو كملف PDF

* Flexible API for custom integrations
  واجهة برمجية مرنة للتكاملات المخصصة

* Send text messages and custom files
  إرسال رسائل نصية وملفات مخصصة

Setup | الإعداد:
----------------
1. Create a Telegram Bot via @BotFather
   أنشئ بوت تيليجرام عبر @BotFather

2. Get the Bot Token and add it in Settings
   احصل على توكن البوت وأضفه في الإعدادات

3. Get your Chat ID and configure it
   احصل على معرف المحادثة وأضفه

4. Configure which reports to send and when
   حدد التقارير المراد إرسالها ومتى

Developed by Yousif Shakir | تطوير يوسف شاكر
    """,
    'author': 'Donia Link',
    'website': 'https://www.donialink.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/telegram_report_schedule_views.xml',
        'views/telegram_daily_summary_views.xml',
        'views/pos_session_views.xml',
        'views/telegram_menus.xml',
        'data/ir_cron_data.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 10,
}
