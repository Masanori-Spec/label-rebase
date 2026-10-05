# Independent verification

Run `python3 -m unittest discover -s oracle -p 'test_*.py' -v`.

The Python oracle does not import the JavaScript implementation. It uses the
standard-library CSV reader, `Decimal` arithmetic, SHA-256, XML reader and ZIP
reader. The tested program is invoked through CLI subprocesses. The export CLI
is an adapter to the real export path, not a reference algorithm.

## Evidence

- `fixtures/canonical-expected.csv` contains handwritten expected results:
  A follows to (22, 28), B stays at (112, 8), C remains automatic, hidden D
  follows to (342, 8), removed E disappears, N is new/automatic, and `007`/`7`
  remain distinct keys
- `reference.py` independently calculates point-to-label offsets with exact
  decimal arithmetic in an explicit 100-digit context; output coordinates are
  compared with exact Decimal equality. A handwritten 29/30-place boundary
  fixture includes near-1e12 coordinates and 2e-30 offsets. Additional exact
  regressions cover 1e12-to-1e-30 cancellation and carry to an integer
- Input tests cover duplicate headers/keys, blank keys, malformed CSV, partial
  label coordinates, invalid numbers, missing mappings/decisions, invalid CRS,
  prototype-like keys, leading zeroes, rotation and hidden-state preservation
- EPSG:3857, EPSG:3395 and UTM boundary codes are checked. Visibility aliases
  blank/0/1/true/false/TRUE/FALSE normalize across keep/follow/reset/auto
- Partial mapping overrides merge the documented defaults in both solve and
  full export round-trip tests
- V1 intentionally rejects blank and multiline label text. Unicode, commas,
  escaped quotes, XML-sensitive characters and BOM/CRLF input are tested
- Metamorphic checks use eight independent row permutations, regenerated and
  duplicate FIDs, and two global translations
- Bundle tests independently read exported CSV, CSVT, QML, QGS, source hashes,
  receipts, saved input/decisions and ZIP contents
- Deliberate corruption tests reject wrong offsets, coerced keys, wrong CSVT
  types, invalid label bindings, absolute paths, mismatched CRS, corrupt hashes,
  wrong receipts, changed saved input, stale ZIP contents and path traversal.
  Each test asserts its intended failure reason; stale ZIP contents cannot
  mask an undetected CSV/XML/receipt mutation

## Bundle verification

`python3 scripts/verify-bundle.py artifacts/demo`

The verifier uses `input.json` when available, otherwise the saved input and
choices in `labelrebase-project.json`. An external request can be supplied with
`--input request.json`.

For an adversarial fixture through the same export path:

`node scripts/export-demo.mjs artifacts/canonical oracle/fixtures/canonical.json`

`python3 scripts/verify-bundle.py artifacts/canonical`

This establishes structural and numerical consistency, including reproducible
source hashes. It does not establish the authenticity of an input document,
render a map, prove actual QGIS placement, or replace the separate native QGIS
gate. Automatic labels can collide or be suppressed by QGIS.
