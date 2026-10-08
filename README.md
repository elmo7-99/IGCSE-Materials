# IGCSE Order Automation

A self-hosted order workflow for study materials: registration, package confirmation, delivery address, payment-receipt review, printing, packing, dispatch and delivery. Arabic and English messages, an Arabic administration dashboard, Google Forms/Sheets intake, and optional n8n orchestration.

**Status: locally tested MVP. Live WhatsApp, bank settlement and courier integrations require configuration. Making this repository public does not run the service, and GitHub Pages cannot host this Python backend.**

## Run locally

Python 3.11+; no runtime packages to install.

```bash
python setup.py
python server.py
```

Open http://127.0.0.1:8080 and enter `ADMIN_API_KEY` from your local `.env`. Never commit that file. Keep `SEND_LIVE=false` while configuring and testing. A persistent server with HTTPS is needed for Google and Meta callbacks.

The bundled selling-price catalog is an initial catalog, not a guarantee of availability. Confirm it, delivery fees, payment account, catalog image links and approved WhatsApp templates before accepting live orders. Runtime settings persist in `data/config.json` and are excluded from Git.

## Integrations

- `integrations/google-forms.gs`: configure `SOURCE_SPREADSHEET_ID`, `SOURCE_TAB`, `ORDERS_BASE_URL`, `INTAKE_API_KEY`, and optionally `DEFAULT_LANGUAGE` in Apps Script properties. Run the setup function only after configuring the HTTPS endpoint. It adds a WhatsApp order-update consent question and registration/retry triggers. Existing responses are not bulk-messaged.
- `integrations/n8n-operations.json`: import and configure protected credentials for reminder/dispatch requests.
- `integrations/n8n-intake.json`: optional authenticated registration ingress.
- `compose.yaml`: persistent volumes, localhost-only host ports, optional n8n with a manually selected image version.

Receiving a receipt does not confirm funds. An operator must check the bank and approve a unique transaction reference. Printing and packing confirmations precede dispatch. Separate active orders for the same guardian require explicit order selection; automatic cart consolidation is not implemented.

## Tests

```bash
python -m unittest discover -s tests -v
```

The included GitHub Actions workflow tests Linux and Windows on Python 3.12 and 3.14 after upload. These CI runs have not executed yet in this prepared repository.

## Documentation

- [Arabic guide](README_AR.md)
- [Sheet and production workflow](docs/VERSION_2_AR.md)
- [API](docs/API.md)
- [Template setup](docs/WHATSAPP_TEMPLATES.md)
- [Validation](docs/VALIDATION.md)
- [Public release review](docs/PUBLIC_RELEASE_REVIEW.md)

MIT license applies to this original application code. n8n and other optional third-party platforms retain their own licenses.
