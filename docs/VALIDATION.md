# Validation — 2026-10-08

47 automated tests passed using Python unittest: 27 original business-engine tests, 10 HTTP integration tests and 10 version-2 tests. Tests use isolated temporary SQLite databases, synthetic registrations and dry mode. No messages were sent to customers.

Verified: end-to-end registration → package/quantity → location → address → receipt → reviewed funds → preparation → shipping → delivery; price totals; idempotent registration/message handling; multiple orders per parent with explicit session selection; missing configuration; consent and opt-out; staff handoff; receipt rejection; duplicate bank references; dispatch guard; template-vs-text behavior; old webhook timestamps; dry mode; uncertain sends; message order; one reminder; admin/intake separation; Meta signature and handshake; dashboard HTTP response; service startup and shutdown.

Not verified live: Meta template approval or actual send, Meta media download/archive, bank settlement, courier delivery, Google Apps Script permissions/triggers, n8n import/execution, Docker build/Compose, browser layout or mobile usability, production load, and Chatwoot integration. No claim of production readiness or full autonomous settlement is made.

The catalog has 16 entries parsed from the supplied final pricing document. Prices are included; delivery charges and bank-holder/IBAN are intentionally unconfigured. WhatsApp credentials and image URLs are absent. The package starts in dry mode and cannot silently send live messages.

Version 2 additionally verifies saved-address confirmation, requiring building details for a map-only address, short confirmation mapping, refusing to substitute an unpriced AS request with OL, separating multiple orders and global opt-out, creating a production order only after verified funds, packing before dispatch, and correctly targeting internal recipients independently of customer opt-out. Google Sheet metadata and A1:J206 were read to ground field mapping; no live Sheet rows were edited, no Form was changed and no Apps Script was installed.
