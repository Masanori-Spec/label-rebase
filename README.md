# LabelRebase

Carry manually positioned QGIS point labels into a refreshed CSV by an explicit stable key. Choose **follow the point**, **keep the map position**, or **reset to automatic** for each moved pinned label. Old feature IDs and row positions are never identities.

**Status: native interoperability gate in progress. This early source snapshot is not a verified release.**

The generated bundle contains typed CSV, a minimal authored QML style, a relative-path QGIS project, a source-hashed decision receipt and a reusable project JSON. Keys remain strings: `007` and `7` are different. Hidden labels remain hidden. New features use automatic placement; removed keys appear in the receipt.

## Contract

- Input: old CSV with key, point X/Y, label X/Y, optional rotation and show; new CSV with key, point X/Y and single-line label text
- Both datasets and label coordinates must use the exact same explicitly declared supported projected CRS
- Supported CRS: EPSG:3857, EPSG:3395 and WGS 84 UTM EPSG:32601–32660 / 32701–32760
- A pair of blank label coordinates means automatic placement. One blank coordinate is invalid
- Duplicate or missing keys, malformed CSV, non-finite numbers, mismatched CRS and unresolved choices block export
- Coordinates: finite decimals within ±10¹², up to 30 digits; maximum 5,000 rows and 2 MB text per CSV
- Extra input columns are not carried into the minimal native output; new point geometry and label text are preserved

This is a reconciliation aid, not a source-style round-trip. It does not read QGZ/QGD, infer keys, reproject, preserve arbitrary styles, handle multiline/rule-based/polygon labels, or guarantee collision-free labels. Review the result in QGIS before operational use. The source CSV CRS is declared by the user and cannot be inferred reliably from its values.

## Development

Node 22 or 24, Python 3. `npm ci --ignore-scripts`, `npm run check`. Generate the native demo with `node scripts/export-demo.mjs`. Hosted native verification uses Ubuntu's distribution-maintained `python3-qgis`; QGIS and fonts are runtime-only and not distributed in this repository's source artifact. See the workflow for the exact consumer route.

## Product distinction

QGIS already supports auxiliary label storage, joins and manual expressions. LabelRebase narrows the task to stable-identity reconciliation across a data refresh, explicit per-label movement decisions, blocked ambiguous inputs, and a portable, auditable native result. It does not claim new cartographic algorithms or patentability. See `docs/sources.md`.
