# Native QGIS contract and hosted gate

LabelRebase exports a **new, minimal style for single-line point labels**. It does not preserve arbitrary source QML, auxiliary storage, callouts, rules, rich text, symbol-dependent placement, layouts, or a pre-existing QGIS project. Coordinates must use the same declared supported projected CRS. No reprojection occurs. The native fixture is EPSG:3857.

## Generated bundle

Keep these files together when moving the folder:

- `rebased.csv`: point geometry columns and label data
- `rebased.csvt`: explicit provider types, including String keys
- `rebased.qml`: the minimal authored labeling and marker style
- `rebased.qgs`: a project containing the same labeling settings and a relative CSV datasource

The ordered CSV schema is:

| Field | CSVT type | Meaning |
| --- | --- | --- |
| stable_key | String | Exact identity; `007` and `7` remain different |
| point_x, point_y | Real | New point geometry coordinates |
| label_text | String | Literal, single-line label text |
| label_x, label_y | Real | Explicit label anchor; both blank means automatic |
| label_rotation | Real | Native data-defined label rotation |
| label_show | Integer | 1 visible / 0 hidden |
| label_state | String | `pinned` or `auto`, descriptive application state |

The QGIS delimited-text provider uses `point_x` and `point_y` to construct geometry. The QGS datasource is `file:./rebased.csv?type=csv&detectTypes=yes&xField=point_x&yField=point_y&crs=EPSG:3857&spatialIndex=no&subsetIndex=no&watchFile=no`, with XML-escaped ampersands. The project itself stores its CRS. It is not a project that silently substitutes an in-memory layer after import.

## XML structure

The application authors this structure; it does not copy a QGIS distribution or a sample project's style. The QML root is `qgis`, with `labelsEnabled="1"` and `styleCategories="Symbology|Labeling"`. It contains a simple marker renderer and `labeling type="simple"`, then `settings` with:

- `text-style`: literal `label_text`, DejaVu Sans Regular, 10 points, explicit normal weight, no extra letter/word spacing
- `text-format`: no wrapping or rich-text rules
- `placement`: around-point fallback for rows with null position values
- `rendering`: labels enabled and point obstacles disabled
- `dd_properties`: field bindings for `PositionX`, `PositionY`, `LabelRotation`, and `Show`

Modern property collections use **property names**, rather than numeric PAL enum keys, in their XML. For example:

```xml
<dd_properties>
  <Option type="Map">
    <Option name="name" type="QString" value=""/>
    <Option name="type" type="QString" value="collection"/>
    <Option name="properties" type="Map">
      <Option name="PositionX" type="Map">
        <Option name="active" type="bool" value="true"/>
        <Option name="field" type="QString" value="label_x"/>
        <Option name="type" type="int" value="2"/>
      </Option>
    </Option>
  </Option>
</dd_properties>
```

The analogous bindings are `PositionY → label_y`, `LabelRotation → label_rotation`, and `Show → label_show`. Type 2 is a field-backed property. The QGS `projectlayers/maplayer` contains the same renderer and labeling elements, plus its layer ID, name, provider, datasource, extent, and CRS. Opening a QGS must not require separately loading the QML.

## Independent native fixture

The old input has A at (0,0), with label anchor (12,8). A moves to (10,20), and **follow** produces (22,28). B moves from (100,0) to (120,10); **keep** retains its (112,8) anchor. C moves to (205,0) and stays automatic. Hidden D moves from (300,0) to (330,0), so **follow** produces (342,8), with visibility still 0. E is removed. N is new at (400,0) and automatic. Exact-string keys `007` and `7` remain separate at x=500 and x=600, with anchors x=512 and x=612. All base rotations are zero.

The new input order is B, N, D, A, C, 7, 007. The Python oracle independently hard-codes the expected coordinates, text, visibility, and state and authors a memory layer using QGIS APIs. It does not import the application's reconciliation or XML-export code, load the generated QML into the reference layer, or derive expected values from generated results.

## Hosted verification

Run the GitHub Actions native gate, or on a suitable Ubuntu host with its official distribution packages installed:

```sh
node scripts/export-demo.mjs
QT_QPA_PLATFORM=offscreen /usr/bin/python3 scripts/native-qgis.py \
  --bundle artifacts/demo --out artifacts/native
```

Use Ubuntu's `python3-qgis` and `fonts-dejavu-core` packages. The system `/usr/bin/python3` is intentional: an unrelated virtual environment may not include the distro's QGIS bindings. No QGIS or font binaries are bundled with this project or uploaded as evidence. The gate does not require installing a heavy native runtime on the development machine.

The gate verifies:

1. The actual exporter produced CSV, CSVT, QML and QGS with the expected typed schema and relative datasource
2. A real folder move, including spaces in the destination, followed by `QgsProject.read` from an unrelated working directory
3. A valid native point layer whose resolved datasource is the relocated CSV; correct CRS, string keys, geometry, values and all four field bindings
4. Native rendered label polygons and positions for A, B, `007`, and `7` against the independent memory layer, with a same-runtime 1e-7 map-unit tolerance
5. Hidden D and removed E are absent; automatic C and new N are visible and unpinned in this sparse fixture
6. Actual standalone QML import reproduces the pinned results
7. Reversing the physical CSV order really changes provider FIDs, while stable-key values and pinned label polygons remain correct
8. A temporary CSV subset containing only numeric-looking keys `007` and `7`, with the actual QGS/QML/CSVT unchanged, still imports both keys as distinct exact Strings and preserves their pinned polygons. This avoids a false assurance from the mixed alphabetic/numeric main fixture, which could infer a string type without CSVT
9. Native positive controls made only in temporary copies: setting D's show field to 1 renders it at its expected position; changing B's rotation to 25 degrees changes its native rendered polygon consistently with a separately authored reference

The controls in steps 8–9 test native typed-import and field-binding behavior; they are not represented as additional exporter fixtures. Automatic collision placement is deliberately **not** required to match exactly. Results can vary with QGIS, Qt, fonts, extent and rendering settings. Visibility in this small sparse fixture is not a guarantee that arbitrary automatic labels will never collide or be suppressed.

## Evidence and failure behavior

`artifacts/native/native-result.json` records `passed`, each completed check, exact input SHA-256 hashes, QGIS/Qt/PyQt/Python/GDAL and package versions, requested and resolved font, native values, changed provider FIDs, rendered label bounds, comparisons, and GitHub commit/run identifiers when available. On failure it records the exception and exits nonzero. There is no missing-runtime skip that reports success.

Seven PNGs show the relocated project, independent reference, separately imported QML, reordered CSV, numeric-looking-only key subset, visible/rotated control, and its independent reference. PNGs document the actual native rendering; the numeric polygon comparison is the position oracle. A successful source syntax check is not a native import/render pass. Only a successful native run for the relevant commit establishes that result.

## Primary references

- [QGIS 3.34 property-collection serialization](https://api.qgis.org/api/3.34/qgspropertycollection_8cpp_source.html): named property maps and XML variant serialization
- [QGIS 3.34 field-property representation](https://api.qgis.org/api/3.34/qgsproperty_8cpp_source.html): active state, field name, and property type
- [QGIS 3.34 PAL read/render source](https://api.qgis.org/api/3.34/qgspallabeling_8cpp_source.html): label settings, data-defined coordinates/visibility/rotation and null-coordinate fallback
- [QGIS 3.34 text-format reader](https://api.qgis.org/api/3.34/qgstextformat_8cpp_source.html): explicit font attributes and units
- [QgsLabelPosition](https://api.qgis.org/api/3.34/classQgsLabelPosition.html): rendered corner points, bounds geometry and pin/visibility state
- [QgsLabelingResults](https://api.qgis.org/api/3.34/classQgsLabelingResults.html): labels returned by the native renderer
- [QGIS project datasource example and version discussion](https://github.com/qgis/QGIS/issues/48587): QGIS-written `file:./` delimited-text project paths
- [QGIS label settings manual](https://docs.qgis.org/3.34/en/docs/user_manual/style_library/label_settings.html): data-defined placement and collision behavior
