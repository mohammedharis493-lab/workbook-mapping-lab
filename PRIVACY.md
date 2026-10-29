# Privacy and release policy

**Public repository contains code + intentionally fabricated datasets only.** Real client files are never committed, including renamed files, blurred screenshots, 'anonymised' financial statements, old Git objects, or workbook contents.

## For each new entity (local/private workflow)

1. Confirm the exact source folder and secure a read-only backup.
2. Copy files into a **private working folder** outside the public repo.
3. Inventory all files, including hidden sheets, comments, external links, images, document metadata, print headers and embedded attachments.
4. Build a local mapping using private actual data. Do not send private data into public GitHub issues, logs or Actions.
5. For public regression testing, create a **fresh synthetic fixture from scratch** using generic captions and fabricated numbers. Do not preserve real amounts, payment dates, addresses, filenames, unique ratios or sequences.
6. Scan public materials with `tools/check_public_repo.py`, then have a person review the exact diff for residual identifiers and business confidentiality.
7. Commit only approved synthetic fixtures and code. If sensitive information is accidentally committed, treat it as a disclosure even if the commit is later deleted; rotate affected credentials and follow the organisation's incident process.

## Sensitive information

Names, family/partner/shareholder details, PAN, Aadhaar, GSTIN, CIN, phone/email, postal addresses, bank accounts/IFSC, tax IDs, UDIN/QR, contracts, financial figures, transaction narrations, workbook formula links, comments, author names and hidden sheets are all in-scope. Supplier / auditor / director names are also sensitive for our release purposes.

A regex scanner cannot prove that data is de-identified. Privacy decisions require human approval.