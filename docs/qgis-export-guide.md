# Prepare QGIS inputs / QGIS からの書き出し

## Before exporting

Work on a copy of your project. This tool accepts only single-point features and simple single-line labels. Keep a stable, unique text identifier that persists between data deliveries. A provider FID, row number or nearest point is not a stable identifier. Preserve leading zeroes and whitespace exactly.

The old point X/Y, old manual label X/Y, and new point X/Y must be expressed in the same projected coordinate frame. Check the layer CRS and project CRS in QGIS. Do not merely rename a CRS declaration to make different coordinates match. If they differ, prepare/reproject the coordinates in QGIS yourself before using this tool; LabelRebase performs no reprojection. The label-coordinate frame must also be verified from the source project's labeling settings.

## Old snapshot

1. Open the point layer's Properties → Labels. Under Placement, inspect the data-defined override for Position X and Position Y. Find the actual field names used by the source project. Rotation and Show are optional; expressions or rule-based settings must be resolved to plain values before export.
2. If placement is stored in auxiliary fields, open Properties → Auxiliary Storage → Auxiliary Layer → Export. QGIS can export these attributes with the original geometry. Verify the exported attribute table includes the stable key and the position fields; use the original layer's Export → Save Features As when all needed fields are already available there.
3. In the vector export dialog, choose CSV and UTF-8. Choose the verified projected CRS and geometry option AS_XY. Include the stable key, manual label X/Y and any optional rotation/show fields. Save the export outside this tool's source folder. The resulting geometry fields may be called X/Y rather than x/y: use the column mapping controls.
4. Check two manually placed labels by comparing the exported coordinate values to their source overrides. Both blank manual coordinates mean automatic placement. One blank coordinate is rejected. A hidden label should have Show=0/false. Rotation defaults to zero and Show defaults to visible when their columns are omitted.

## New snapshot

Export the refreshed point layer as CSV with UTF-8 and AS_XY in the same verified projected CRS. Include the same stable key definition and a single-line label-text field. Do not convert the key column to numbers through a spreadsheet. The new rows may be in any order.

## After rebasing

Unzip the bundle into one folder and open rebased.qgs in QGIS. Keep rebased.csv and rebased.csvt beside it. The project embeds a minimal authored style; rebased.qml is the same style for applying manually. Inspect the label positions and visibility at the intended map scale. Automatic labels can collide or be suppressed by QGIS. Original fonts, rule-based placement and other source styling are not preserved.

The project JSON contains the original CSV text, mappings, CRS declarations and choices. Keep it private if the inputs are private. Decisions JSON includes source-text SHA-256 values, decisions and removed/new key receipts. Hashing is over the UTF-8 text loaded by the app, not a promise to preserve a non-UTF-8 file's original byte encoding.

## 日本語の要点

- 元のプロジェクトのコピーを使い、更新の前後で変わらない一意の文字列キーを用意します。FID や行番号は使いません。007 と 7 は別のキーです
- 旧点・手動ラベル・新点の座標系を確認し、同じ投影座標系で CSV を用意します。座標系名を付け替えるだけでは変換になりません
- レイヤのプロパティでラベル位置 X/Y の参照フィールドを確認します。補助記憶域の場合は補助レイヤをエクスポートできます
- CSV・UTF-8・AS_XY で書き出し、アプリの列の割り当てでキー、点座標、ラベル位置を指定します。回転・表示列は省略できます
- 更新後の CSV には同じキー、点 X/Y、1 行のラベル文字列を含めます
- 出力を展開し、同じフォルダの rebased.qgs を開いて配置を確認します。元の任意のスタイルや衝突回避は保証しません

## References

QGIS auxiliary export and vector export are documented by the QGIS project: https://docs.qgis.org/3.40/en/docs/user_manual/working_with_vector/vector_properties.html#auxiliary-storage-properties and https://docs.qgis.org/3.40/en/docs/user_manual/managing_data_source/create_layers.html#save-layer-from-an-existing-file . Menu labels can vary by QGIS version and language; verify the selected fields rather than relying on automatically generated auxiliary field names.
