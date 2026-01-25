# Telegram Reports | تقارير تيليجرام

Automatically send Odoo reports to Telegram chats and groups.

إرسال تقارير أودو تلقائياً عبر تيليجرام.

![Odoo Version](https://img.shields.io/badge/Odoo-18.0-blue)
![License](https://img.shields.io/badge/License-LGPL--3-green)

---

## Features | المميزات

### English
- ✅ **Bot Configuration** - Easy setup of Telegram Bot token and Chat ID
- ✅ **Scheduled Reports** - Send reports daily, weekly, or monthly
- ✅ **Any Odoo Report** - Works with any PDF report in Odoo
- ✅ **Flexible Filters** - Define which records to include using domain filters
- ✅ **Custom Captions** - Customize the message caption with templates
- ✅ **Manual Sending** - Send reports on-demand with one click
- ✅ **API for Developers** - Easy-to-use API for custom integrations
- ✅ **Arabic Support** - Full Arabic language translation

### العربية
- ✅ **إعداد البوت** - إعداد سهل لتوكن البوت ومعرف المحادثة
- ✅ **تقارير مجدولة** - إرسال التقارير يومياً أو أسبوعياً أو شهرياً
- ✅ **أي تقرير أودو** - يعمل مع أي تقرير PDF في أودو
- ✅ **فلاتر مرنة** - تحديد السجلات باستخدام فلاتر التصفية
- ✅ **تسميات مخصصة** - تخصيص رسالة التقرير باستخدام قوالب
- ✅ **إرسال يدوي** - إرسال التقارير بضغطة زر
- ✅ **واجهة للمطورين** - واجهة برمجية سهلة للتكاملات المخصصة
- ✅ **دعم العربية** - ترجمة عربية كاملة

---

## Installation | التثبيت

1. Place the module in your Odoo addons directory
2. Restart Odoo
3. Update Apps List
4. Install "Telegram Reports"

---

## Setup | الإعداد

### Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the **Bot Token** provided

### Step 2: Get Your Chat ID

1. Add your bot to a group OR start a private chat with it
2. Send any message to the bot/group
3. Open this URL in your browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
4. Find `"chat":{"id": YOUR_CHAT_ID}` in the response

### Step 3: Configure in Odoo

1. Go to **Telegram Reports → Configuration → Settings**
2. Enter your **Bot Token**
3. Enter your **Default Chat ID**
4. Click **Test Connection** to verify

### Step 4: Create Report Schedules

1. Go to **Telegram Reports → Report Schedules**
2. Click **New**
3. Select the report to send
4. Configure the schedule (daily, weekly, monthly)
5. Set filter criteria if needed
6. Save and activate

---

## Developer API | واجهة المطورين

### Send a Text Message

```python
telegram = self.env['telegram.service']
telegram.send_message("Hello from Odoo!", chat_id="123456789")
```

### Send a Document

```python
telegram = self.env['telegram.service']
telegram.send_document(
    document=pdf_content,  # bytes or base64
    filename="report.pdf",
    caption="Here's your report!"
)
```

### Send an Odoo Report

```python
telegram = self.env['telegram.service']
telegram.send_pdf_report(
    'sale.report_saleorder',  # Report XML ID
    [order.id],               # Record IDs
    caption="Sales Order Report"
)
```

### Send Report by Action ID

```python
telegram = self.env['telegram.service']
telegram.send_report_by_action(
    report_action_id=123,
    record_ids=[1, 2, 3],
    caption="Monthly Report"
)
```

---

## Caption Template Variables

Use these variables in your caption templates:

| Variable | Description |
|----------|-------------|
| `{report_name}` | Name of the report |
| `{date}` | Current date (YYYY-MM-DD) |
| `{record_count}` | Number of records in report |

Example: `📊 {report_name}\n📅 {date}\n📝 {record_count} records`

---

## Module Structure

```
telegram_reports/
├── __init__.py
├── __manifest__.py
├── README.md
├── data/
│   └── ir_cron_data.xml
├── i18n/
│   └── ar.po
├── models/
│   ├── __init__.py
│   ├── res_config_settings.py
│   ├── telegram_report_schedule.py
│   └── telegram_service.py
├── security/
│   └── ir.model.access.csv
├── static/
│   └── description/
│       └── icon.svg
└── views/
    ├── res_config_settings_views.xml
    ├── telegram_menus.xml
    └── telegram_report_schedule_views.xml
```

---

## Dependencies

- Odoo 18.0 Community or Enterprise
- Python `requests` library (usually pre-installed)

---

## Support | الدعم

For issues and feature requests, please create an issue on GitHub.

للمشاكل وطلبات الميزات، يرجى إنشاء issue على GitHub.

---

## Author | المطور

**Yousif Shakir** | يوسف شاكر

**Company**: Donia Link | دنيا لينك

**Website**: [www.donialink.com](https://www.donialink.com)

---

## License | الرخصة

LGPL-3

---

## Changelog

### Version 18.0.1.0.0
- Initial release
- Telegram bot configuration
- Scheduled report sending
- Manual report sending
- Developer API
- Arabic translation
