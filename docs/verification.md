# Verification status

## Passed before the full release-candidate publication

- 22 Node unit tests: canonical rebase, explicit-choice gating, hidden/reset semantics, decimal precision, malformed CSV/number/CRS rejection, prototype-like keys, native CRS IDs, project parsing and static mount containment
- 51 independent Python black-box methods: handwritten Decimal reference, adversarial inputs, row permutation/FID regeneration/global translation, exact CSV/XML/JSON/ZIP output checking, Unicode and quoted text, plus16 deliberate corruption-rejection cases
- Full dependency-free `npm run check` on local Node24.19.0 and Python3; standalone bundled JavaScript syntax check
- 5,000-row exact-offset/ZIP boundary under a256 MB Node heap (about0.45 s on this local run; not a general performance promise)
- Initial real QGIS3.34.4/Qt5.15.13 native gate at commit2598d28c9e1db398c7924c8e0085b04d07ce1ad1 and run37264195166: https://github.com/Masanori-Spec/label-rebase/actions/runs/37264195166
- Native project was physically relocated into a folder containing spaces and opened from an unrelated working directory. QGS/CSV/CSVT fields, CRS and geometry passed; pinned polygons matched an independently authored memory layer with maximum corner distance0. HiddenD, visible/rotated controls, standalone QML, changed provider FIDs and numeric-only007/7 controls passed

The first native gate failed because minimal CRS XML did not enable project projection or include real native CRS IDs. This was fixed using QGIS's official documented readers and legacy ID map. The native assertions were kept intact; the subsequent run passed. The failure was not reclassified as success.

## Pending for this full UI revision

- Hosted Node22/24 matrix
- Authored Playwright QA against the actual single-file distributable, in a sandboxed browser on a non-root GitHub-hosted Ubuntu22.04 runner
- Visual review of JA/EN desktop and390px mobile screenshots
- Real QGIS import/render of the exact browser-downloaded bundle under Ubuntu24.04

The browser harness explicitly verifies the sandbox launch arguments, explicit choices, mappings, clear/import/stale-result behavior, keyboard names/focus, locale preservation, malicious text escaping, and independent Python parsing of the actual ZIP. These are authored checks, not claimed passes until the hosted run finishes. No local heavy QGIS or shared browser was used.

## Reproduce

Run `npm ci --ignore-scripts` then `npm run check`. CI installs test-only Playwright1.56.0 and runtime-only distribution QGIS/fonts. The static production HTML has zero third-party runtime dependencies. Native JSON and PNG receipts contain only our synthetic data; dependencies and caches are excluded from source distribution.

## Independent review corrections before the full candidate commit

Read-only review found and reproduced edge cases beyond the initial suite: source precision limits incorrectly constrained intermediate decimal arithmetic; a carry could be counted before normalization; Python Decimal default precision rounded valid 29/30-digit expectations; the oracle omitted a supported CRS and visibility aliases; noncanonical EPSG IDs and decimal values just beyond the rotation limit slipped through. These were corrected with specific regressions. Preview errors now disable outputs before rendering; byte limits agree across paste/file/project paths. Corruption tests require the intended semantic failure reason, and CI verifies the committed standalone file equals a fresh deterministic build.
