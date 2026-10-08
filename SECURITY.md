# Security and operations

Do not post tokens, customer information, bank records or receipt images in public issues. The application stores runtime settings, customer data and receipt files under `data/`; keep it private and back it up separately from the source repository.

Use distinct strong administration/intake keys. Keep Meta and n8n credentials in server secrets or a local `.env`, never Git. Use an HTTPS reverse proxy and restrict administrator access. Do not expose receipt/database directories as static files.

Keep dry mode enabled until a complete test order has passed through the actual Meta account. An uncertain send must be reconciled with the provider before retry. An uploaded payment receipt is not evidence of settled funds; bank confirmation is a human or trusted-payment-system decision.

This MVP uses Python's standard HTTP server behind a reverse proxy and has not undergone a production load test or independent security audit. Limit request rates at the proxy and monitor delivery/archive failures before taking customer traffic.
