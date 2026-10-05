# LabelRebase

Carry manually positioned QGIS point labels into a refreshed CSV by an explicit stable key. Choose **follow the point**, **keep the map position**, or **reset to automatic** for each moved pinned label. Old feature IDs and row positions are never identities.

**Status: verified prototype. The Node 22/24 checks, 29 sandboxed browser checks, and real QGIS 3.34.4 checks on CLI and browser-download output have passed.**

The generated bundle contains typed CSV, a minimal authored QML style, a relative-path QGIS project, a source-hashed decision receipt and a reusable project JSON. Keys remain strings: `007` and `7` are different. Hidden labels remain hidden. New features use automatic placement; removed keys appear in the receipt.

## Contract

- Input: old CSV with key, point X/Y, label X/Y, optional rotation and show; new CSV with key, point X/Y and single-line label text
- Both datasets and label coordinates must use the exact same explicitly declared supported projected CRS
- Supported CRS: EPSG:3857, EPSG:3395 and WGS 84 UTM EPSG:32601–32660 / 32701–32760
- A pair of blank label coordinates means automatic placement. One blank coordinate is invalid
- Duplicate or missing keys, malformed CSV, non-finite numbers, mismatched CRS and unresolved choices block export
- Coordinates: finite decimals within ±10¹², up to 30 digits; maximum 5,000 rows, 256 columns and 2 MB UTF-8 per CSV (column names: at most 256 characters)
- Extra input columns are not carried into the minimal native output; new point geometry and label text are preserved

This is a reconciliation aid, not a source-style round-trip. It does not read QGZ/QGD, infer keys, reproject, preserve arbitrary styles, handle multiline/rule-based/polygon labels, or guarantee collision-free labels. Review the result in QGIS before operational use. The source CSV CRS is declared by the user and cannot be inferred reliably from its values.

## Use

Open `dist/index.html` directly in a modern browser; it is a self-contained, offline-capable app. Japanese and English are available. Start with **Try the example**, compare the snapshots, then choose policies for A, B and D. Your inputs are not uploaded. The ZIP and saved project both contain the original CSVs in the project JSON.

Column mapping is explicit. Blank optional rotation/visibility mappings default to 0/visible. A pair of blank label coordinates stays automatic; existing automatic-label rotation and hidden state are preserved. Reset clears manual position and rotation while keeping visibility. Source edits invalidate old results immediately. See `docs/qgis-export-guide.md` for QGIS preparation and coordinate-frame checks.

## Development

Node 22 or 24, Python 3. `npm ci --ignore-scripts`, `npm run check`. Generate the native demo with `node scripts/export-demo.mjs`. Hosted native verification uses Ubuntu's distribution-maintained `python3-qgis`; QGIS and fonts are runtime-only and not distributed in this repository's source artifact. See the workflow for the exact consumer route.

## Product distinction

QGIS already supports auxiliary label storage, joins and manual expressions. LabelRebase narrows the task to stable-identity reconciliation across a data refresh, explicit per-label movement decisions, blocked ambiguous inputs, and a portable, auditable native result. It does not claim new cartographic algorithms or patentability. See `docs/sources.md`.

## Verification

The early native gate passed at commit `2598d28c9e1db398c7924c8e0085b04d07ce1ad1`: https://github.com/Masanori-Spec/label-rebase/actions/runs/37264195166 . QGIS 3.34.4 read the relocated project and its typed CSV, rendered it, matched pinned-label polygons exactly against an independently authored native layer, preserved numeric-only keys `007`/`7`, and verified visibility, rotation and FID-reordering controls. This is a specific tested runtime, not a claim that every QGIS release is supported.

The full workflow separately runs a dependency-free core/independent oracle on Node 22/24, sandboxed Chromium on Ubuntu 22.04, then native QGIS on Ubuntu 24.04 against both CLI output and the **actual browser download**. The full verified run is https://github.com/Masanori-Spec/label-rebase/actions/runs/37266880133 at source commit `e0e2525c09deb54cda4f9d7fff99157ea296e492`. See `docs/verification.md` and the receipts/screenshots in `evidence/`.
