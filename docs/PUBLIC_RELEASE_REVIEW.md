# Public release review — 2026-10-08

Status: prepared locally; not yet uploaded to GitHub or deployed.

53 local automated tests passed: the original 47 workflow/HTTP tests plus 6 publication/configuration regression checks. No live WhatsApp, Google Apps Script, bank or courier transaction was performed.

Changes for this public release:

- Removed the actual customer-registration spreadsheet identifier from all public files. The Apps Script reads it from private Script Properties instead.
- Included no customer exports, receipts, databases, local .env, cloud credentials or actual bank-account details.
- Added .gitignore and .dockerignore rules to exclude runtime/private files and accidental document/CSV exports.
- Added strict configuration checks for package lists and delivery fees, early authentication before reading application request bodies, a connection timeout, and a startup guard requiring distinct admin/intake secrets.
- Preserved the UTF-8 fix, deterministic integer-price arithmetic, Meta webhook signature verification, dry mode, manual verification of bank funds, unique payment references, internal recipient routing, and printing/packing gates.
- Prepared a GitHub Actions matrix for Linux/Windows and Python 3.12/3.14; remote CI has not run yet.

Checks performed: full unit/HTTP regression suite, Python compilation, release-file review and exact scan for the source spreadsheet identifier. This is a scoped review, not an independent penetration test or security certification. Live integration, Docker execution, production load and browser rendering remain unverified.

Known launch dependencies: a persistent HTTPS server; approved WhatsApp templates and Meta credentials; current package availability; teacher image URLs; city fees; bank holder/IBAN; actual internal-recipient phone numbers. GitHub hosts source and CI; publishing the repository does not execute this backend.

For a public source release, review school/organization branding and catalog availability before advertising a hosted service. The catalog contains selling prices only and no printing-cost or profit analysis.
