# WhatsApp templates — setup specification

These are proposed templates, not approved Meta templates. Approval, classification and the exact available language code must be verified in the business account. The sender uses one dynamic body parameter, removes line breaks from it and blocks payloads over 900 characters. If Meta rejects this parameter structure, replace it with a template with named business fields and update provider.py accordingly. No approval is guaranteed.

## Intro (image header)

Suggested English name: igcse_order_intro_en. Header: IMAGE (sample must be supplied in Meta).

Body:

Hello from Egyptian Club – Al Ain. We are following up on your study materials request: {{1}}. Please confirm your choice. Reply STAFF for help or STOP to stop updates.

Suggested Arabic name: igcse_order_intro_ar. Header: IMAGE.

مرحبًا من النادي المصري – العين. نتابع طلبك للكتب التعليمية: {{1}}. يرجى تأكيد اختيارك. للمساعدة أرسل موظف، ولإيقاف التحديثات أرسل إيقاف.

## Updates (no header)

Suggested English name: igcse_order_update_en.

An update on your Egyptian Club – Al Ain order: {{1}}. Reply STAFF if you need help or STOP to stop updates.

Suggested Arabic name: igcse_order_update_ar.

تحديث بخصوص طلبك لدى النادي المصري – العين: {{1}}. للمساعدة أرسل موظف، ولإيقاف التحديثات أرسل إيقاف.

The actual approved names go in config templates.ar/en.intro/update; language codes go in template_language_codes. The catalog image HTTPS link comes from packages.image_url. No credentials belong in exported n8n workflows.

Never interpret a Form submission as a WhatsApp message opening a service window. Test one approved template and one customer reply with the real business account before enabling the remaining queue.

## Internal workorder template (Arabic, no header)

Proposed name: igcse_internal_workorder_ar. Body: أمر تجهيز داخلي لدى النادي المصري – العين: {{1}}. يرجى اتباع تفاصيل الطلب المعتمدة.

Approval is not guaranteed; configure the actual approved name at templates.ar.workorder. Internal recipients must be explicitly configured by the operator. They are never inferred from a customer row. No internal message is sent if those fields are empty.
