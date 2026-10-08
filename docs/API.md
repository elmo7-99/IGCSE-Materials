# API contract

All request bodies are JSON, maximum 1 MiB. Use HTTPS outside localhost.

| Endpoint | Credential | Purpose |
|---|---|---|
| GET /health | none | Mode and health |
| GET / | none | Admin shell; data requires API key |
| POST /api/intake | INTAKE_API_KEY or ADMIN_API_KEY | New registration |
| GET /api/orders | ADMIN_API_KEY | Orders |
| GET /api/orders/{id} | ADMIN_API_KEY | Order, receipts, audit, queue |
| GET /api/config | ADMIN_API_KEY | Current config |
| POST /api/config | ADMIN_API_KEY | Validate and persist config |
| GET /api/workorders | ADMIN_API_KEY | Production queue |
| POST /api/actions | ADMIN_API_KEY | Staff/payment/courier transition |
| POST /api/reminders | ADMIN_API_KEY | One reminder after 24 hours |
| POST /api/dispatch | ADMIN_API_KEY | Dispatch pending messages, or dry preview |
| POST /api/simulate | ADMIN_API_KEY, dry mode only | Simulated WhatsApp message |
| GET /api/receipts/{receipt_id} | ADMIN_API_KEY | Archived receipt bytes |
| GET /webhooks/meta | verification token | Meta handshake |
| POST /webhooks/meta | Meta HMAC-SHA256 | Customer messages and message-status events |

Credentials: Authorization: Bearer KEY. Never expose the admin key to the client integration; use the intake key for Form submissions.

Registration example (synthetic, not a live send):

```json
{"source_id":"sheet-id:row-2","name":"Test Customer","phone":"0551234567","subject":"Chemistry","city":"Sharjah (الشارقة)","teacher":"د. بيتر ألفريد","package":"OL Cambridge J27","lang":"en","consent":true}
```

Confirmation message: CONFIRM CHEM-04 1. A Meta interactive button/list payload may contain the same command string. Then share a WhatsApp location, send the building/apartment address as text, and upload a JPEG/PNG/PDF receipt.

Actions:

```json
{"order_id":"IG-...","action":"approve_payment","funds_verified":true,"bank_reference":"ACTUAL-BANK-REFERENCE"}
```

```json
{"order_id":"IG-...","action":"dispatch","eta":"Confirmed delivery window","tracking":"Actual shipment reference"}
```

```json
{"order_id":"IG-...","action":"deliver","proof":"Actual courier/customer confirmation reference"}
```

Other actions: reject_payment + reason; cancel + reason; pause; resume; retry_catalog + optional teacher; retry_message + message_id + provider_checked=true after provider reconciliation.

Do not hand these admin endpoints directly to an untrusted AI agent or an unsigned external callback. A courier adapter must authenticate the courier event, match the order and tracking ID, then call the appropriate action. No such adapter is preconfigured in this release.

Version 2 registration accepts initial_address, school and student_phone. Supported production actions: mark_printed then mark_packed. With require_packing_confirmation=true, dispatch is rejected until packed. For a parent with multiple active orders, send ORDER IG-... before the next reply; alternatively prefix a text command with the order ID. STOP and STAFF apply to all active orders for that parent.
