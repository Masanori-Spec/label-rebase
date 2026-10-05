# Verification

## Verified source and hosted run

Source commit: `e0e2525c09deb54cda4f9d7fff99157ea296e492`

Full successful run: https://github.com/Masanori-Spec/label-rebase/actions/runs/37266880133

- Node 22 and Node 24: 22 unit tests and 51 independent Python test methods per version
- Chromium 141.0.7390.37: 29 authored browser checks on a non-root GitHub-hosted Ubuntu 22.04 runner, with the browser sandbox enabled and forbidden launch flags independently checked
- QGIS 3.34.4 / Qt 5.15.13 on Ubuntu 24.04: 8 native checks for CLI output and the same 8 for the actual sandboxed-browser download
- Native browser input hashes match the exact extracted download; all 14 native PNG hashes match their receipts
- The committed standalone app matches a fresh deterministic build. Both the hosted HTTP path and direct offline `file://` opening/download passed
- Japanese and English desktop/mobile screenshots were inspected. Inputs, decisions and download controls remain legible at 390 px. The ledger scrolls in its own region; there is no horizontal document overflow

Receipts and four representative screenshots are under `evidence/`. Hosted artifact IDs and SHA-256 values are in `evidence/hosted-verification.json`. These evidence files identify the source commit they tested; later documentation-only commits do not retroactively change the recorded run.

## What the checks establish

The native project was physically relocated into a folder containing spaces and opened from an unrelated working directory. QGS/CSV/CSVT fields, CRS and geometry passed. Pinned-label polygons matched an independently authored native memory layer with maximum corner distance 0. Hidden D, visible/rotated controls, standalone QML, changed provider FIDs and numeric-only 007/7 controls all passed. Automatic labels were checked for identity and automatic status, without claiming deterministic collision placement.

The independent Python oracle does not import producer logic. It uses handwritten expected CSVs and explicit 100-digit Decimal arithmetic for accepted 29/30-digit inputs, cancellation and carry boundaries. It checks row permutation, FID regeneration, global translation, CRS/visibility profiles, partial mappings, Unicode/quoted text, real CSV/XML/JSON/ZIP output, and 16 deliberate corruptions. Corruption cases require their specific semantic failure reason rather than relying on a stale ZIP mismatch.

Browser checks cover explicit-choice gating, column mappings, project round-trip, repeated and malformed imports, immediate stale-result invalidation, input/rotation/CRS errors, locale preservation, optional mappings, keyboard names/focus, literal HTML-like labels, range-error recovery, exact cancellation, responsive layout and actual downloaded ZIPs. No uncaught errors, failed requests or injection dialogs occurred.

A 5,000-row exact-offset export was also checked under a 256 MB Node heap. Local measurements were about 0.4–0.5 seconds, which is not a universal performance promise.

## Defects caught before verification

The first native gate found incomplete CRS XML: project projection needed enabling and native CRS blocks needed the actual legacy system IDs alongside EPSG authority IDs. This was corrected from official QGIS reader/ID references; native assertions were not weakened.

Independent review found a distinction between input precision and arithmetic intermediates, carry normalization, Python Decimal's default precision, CRS/visibility oracle coverage, exact rotation bounds and UTF-8 replay limits. Specific regressions now cover each correction. Visual inspection found an offscreen skip-link capture artifact and ambiguous automatic-label policy wording; both were corrected and the complete hosted suite reran successfully.

## Reproduce and limits

Run `npm ci --ignore-scripts` and `npm run check`. CI installs test-only Playwright 1.56.0 and runtime-only distribution QGIS/fonts. The production HTML has zero third-party runtime dependencies. No local heavy QGIS or shared browser was used for QA.

Native rendering coverage is specifically EPSG:3857 on QGIS 3.34.4 with the synthetic fixture. EPSG:3395 and supported UTM codes have structural/arithmetic coverage; they are not claimed as separately native-render tested. Other QGIS releases, original fonts/styles, multiline/rule-based/polygon labeling, reprojection, operational map accuracy and collision-free placement are outside this verification claim. Review the final map in its intended environment.
