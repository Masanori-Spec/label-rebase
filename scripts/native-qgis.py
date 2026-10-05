#!/usr/bin/env python3
"""Hosted PyQGIS gate for the *actual* exported LabelRebase bundle.

Use Ubuntu's /usr/bin/python3 and python3-qgis, never a replacement implementation.
This script does not generate/fix the production bundle or borrow its style for the
oracle. The only persistent evidence is JSON and PNG; QGIS/fonts stay on the runner.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

# Must precede Qt/QGIS imports. No display server or user QGIS profile required.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QGIS_PREFIX_PATH", "/usr")

FIELDS = (
    "stable_key", "point_x", "point_y", "label_text", "label_x", "label_y",
    "label_rotation", "label_show", "label_state",
)
FILES = ("rebased.csv", "rebased.csvt", "rebased.qml", "rebased.qgs")
# Independently hand-calculated from the committed old/new fixture and decisions.
# No core/export module or generated expected-result file is imported here.
EXPECTED = {
    "A": (10, 20, "Alpha", 22, 28, 0, 1, "pinned"),
    "B": (120, 10, "Bravo", 112, 8, 0, 1, "pinned"),
    "C": (205, 0, "Charlie", None, None, 0, 1, "auto"),
    "D": (330, 0, "Hidden", 342, 8, 0, 0, "pinned"),
    "N": (400, 0, "New", None, None, 0, 1, "auto"),
    "007": (500, 0, "Zero zero seven", 512, 8, 0, 1, "pinned"),
    "7": (600, 0, "Seven", 612, 8, 0, 1, "pinned"),
}
TOLERANCE = 1e-7  # map units, same native runtime/font/settings on both sides


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal_number(actual, expected, label):
    require(math.isfinite(float(actual)), f"{label}: nonfinite value {actual!r}")
    require(abs(float(actual) - expected) <= TOLERANCE,
            f"{label}: got {actual!r}, expected {expected!r}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == list(FIELDS), f"Unexpected CSV schema: {reader.fieldnames}")
        return list(reader)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def check_serialized_contract(bundle):
    for name in FILES:
        require((bundle / name).is_file(), f"Missing actual exporter output: {name}")
    csvt = next(csv.reader([(bundle / "rebased.csvt").read_text().strip()]))
    require([item.lower() for item in csvt] == [
        "string", "real", "real", "string", "real", "real", "real", "integer", "string",
    ], f"CSVT must explicitly type exact keys and nullable label coordinates: {csvt}")
    project_xml = ET.parse(bundle / "rebased.qgs").getroot()
    sources = project_xml.findall("./projectlayers/maplayer/datasource")
    require(len(sources) == 1, "QGS must contain one generated point layer")
    require((sources[0].text or "").startswith("file:./rebased.csv?"),
            f"QGS datasource must be project-relative: {sources[0].text!r}")
    qml = ET.parse(bundle / "rebased.qml").getroot()
    require(qml.find("./labeling/settings") is not None, "QML has no authored label settings")
    return read_csv(bundle / "rebased.csv")


def runtime_info():
    from qgis.core import Qgis
    from qgis.PyQt.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
    from qgis.PyQt.QtGui import QFont, QFontInfo
    from osgeo import gdal
    packages = subprocess.run(
        ["dpkg-query", "-W", "-f=${Package}=${Version}\n", "python3-qgis", "fonts-dejavu-core"],
        capture_output=True, text=True, check=False,
    )
    return {
        "qgis": Qgis.QGIS_VERSION,
        "qgis_version_int": Qgis.QGIS_VERSION_INT,
        "qt": QT_VERSION_STR,
        "pyqt": PYQT_VERSION_STR,
        "python": sys.version.split()[0],
        "gdal": gdal.VersionInfo("RELEASE_NAME"),
        "platform": platform.platform(),
        "distribution_packages": packages.stdout.strip().splitlines(),
        "font_requested": "DejaVu Sans",
        "font_resolved": QFontInfo(QFont("DejaVu Sans", 10)).family(),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    }


def check_layer(layer, expected=EXPECTED):
    from qgis.core import NULL, QgsPalLayerSettings, QgsProperty
    from qgis.PyQt.QtCore import QVariant
    require(layer.isValid(), "Native imported layer is invalid")
    require(layer.crs().authid() == "EPSG:3857", f"Wrong native layer CRS: {layer.crs().authid()}")
    require(layer.fields().names() == list(FIELDS), f"Native field schema: {layer.fields().names()}")
    require(layer.fields().field("stable_key").type() == QVariant.String,
            "stable_key was not imported as String; 007 could collapse into 7")
    require(layer.fields().field("label_x").type() == QVariant.Double,
            "label_x was not imported as nullable Real")
    require(layer.labelsEnabled() and layer.labeling() is not None,
            "Native project/style did not enable labels")
    settings = layer.labeling().settings()
    require(settings.fieldName == "label_text" and not settings.isExpression,
            "Label text must bind to the literal text field")
    bindings = {
        "PositionX": "label_x", "PositionY": "label_y",
        "LabelRotation": "label_rotation", "Show": "label_show",
    }
    for name, field in bindings.items():
        prop = settings.dataDefinedProperties().property(getattr(QgsPalLayerSettings, name))
        require(prop.isActive() and prop.propertyType() == QgsProperty.FieldBasedProperty
                and prop.field() == field, f"Native {name} binding is not {field}")
    rows = {}
    fids = {}
    for feature in layer.getFeatures():
        key = feature["stable_key"]
        require(isinstance(key, str), f"Key {key!r} is not an exact string")
        require(key not in rows, f"Duplicate native key {key!r}")
        require(key in expected, f"Unexpected native feature {key!r}")
        values = expected[key]
        row = {}
        for name, wanted in zip(FIELDS[1:], values):
            actual = feature[name]
            if wanted is None:
                require(actual is None or actual == NULL, f"{key}.{name}: expected NULL, got {actual!r}")
                row[name] = None
            elif isinstance(wanted, str):
                require(actual == wanted, f"{key}.{name}: {actual!r} != {wanted!r}")
                row[name] = actual
            else:
                equal_number(actual, wanted, f"{key}.{name}")
                row[name] = float(actual)
        point = feature.geometry().asPoint()
        equal_number(point.x(), values[0], f"{key}.geometry.x")
        equal_number(point.y(), values[1], f"{key}.geometry.y")
        rows[key] = row
        fids[key] = int(feature.id())
    require(set(rows) == set(expected), f"Imported keys {sorted(rows)} != expected keys {sorted(expected)}")
    require(fids["007"] != fids["7"], "007 and 7 share a native feature")
    return {"rows": rows, "provider_fids": fids, "bindings": bindings}


def independent_layer(expected=EXPECTED):
    """Hand-author memory geometry, values and style through native QGIS APIs."""
    from qgis.core import (
        QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
        QgsPalLayerSettings, QgsProperty, QgsTextFormat, QgsVectorLayerSimpleLabeling,
        QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsUnitTypes,
    )
    from qgis.PyQt.QtCore import QVariant
    from qgis.PyQt.QtGui import QFont, QColor
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Independent hand-authored oracle", "memory")
    types = [QVariant.String, QVariant.Double, QVariant.Double, QVariant.String,
             QVariant.Double, QVariant.Double, QVariant.Double, QVariant.Int, QVariant.String]
    provider = layer.dataProvider()
    require(provider.addAttributes([QgsField(name, typ) for name, typ in zip(FIELDS, types)]),
            "Could not build independent memory fields")
    layer.updateFields()
    features = []
    # Deliberately use an order unlike the generated CSV order.
    for key in sorted(expected):
        values = expected[key]
        feature = QgsFeature(layer.fields())
        feature.setAttributes([key, *values])
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(values[0], values[1])))
        features.append(feature)
    added, _ = provider.addFeatures(features)
    require(added, "Could not add independent memory features")
    layer.updateExtents()
    font = QFont("DejaVu Sans", 10)
    font.setWeight(QFont.Normal)
    font.setItalic(False)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
    font.setWordSpacing(0)
    text_format = QgsTextFormat()
    text_format.setFont(font)
    text_format.setSize(10)
    text_format.setSizeUnit(QgsUnitTypes.RenderPoints)
    text_format.setColor(QColor(20, 30, 40))
    settings = QgsPalLayerSettings()
    settings.fieldName = "label_text"
    settings.isExpression = False
    settings.placement = QgsPalLayerSettings.AroundPoint
    settings.dist = 0
    settings.obstacle = False
    settings.setFormat(text_format)
    for name, field in (("PositionX", "label_x"), ("PositionY", "label_y"),
                        ("LabelRotation", "label_rotation"), ("Show", "label_show")):
        settings.dataDefinedProperties().setProperty(getattr(QgsPalLayerSettings, name),
                                                     QgsProperty.fromField(field))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({
        "name": "circle", "color": "25,110,95,255", "size": "2", "outline_style": "no",
    })))
    return layer


def render(layer, output, name):
    from qgis.core import QgsMapSettings, QgsMapRendererSequentialJob, QgsRectangle
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(layer.crs())
    settings.setExtent(QgsRectangle(-40, -85, 690, 135))
    settings.setOutputSize(QSize(1460, 440))
    settings.setOutputDpi(96)
    settings.setBackgroundColor(QColor("white"))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    errors = [error.message for error in job.errors()]
    require(not errors, f"Native render errors ({name}): {errors}")
    png = output / f"{name}.png"
    require(job.renderedImage().save(str(png), "PNG"), f"Could not save {name} PNG")
    results = job.takeLabelingResults()
    require(results is not None, f"No native labeling results for {name}")
    by_fid = {int(feature.id()): feature["stable_key"] for feature in layer.getFeatures()}
    labels = {}
    for position in results.allLabels():
        if position.isUnplaced:
            continue
        require(position.layerID == layer.id(), "Label result belongs to another layer")
        key = by_fid[int(position.featureId)]
        require(key not in labels, f"Repeated label for single-line point {key}")
        corners = [[point.x(), point.y()] for point in position.cornerPoints]
        require(len(corners) >= 4, f"{key}: label bounding polygon missing")
        require(all(math.isfinite(v) for p in corners for v in p), f"{key}: invalid polygon")
        require(not position.labelGeometry.isEmpty(), f"{key}: native labelGeometry empty")
        labels[key] = {
            "text": position.labelText,
            "pinned": bool(position.isPinned),
            "corners": corners,
            "bounds_wkt": position.labelGeometry.asWkt(12),
            "rotation": position.rotation,
            "width": position.width,
            "height": position.height,
        }
    return {"labels": labels, "png": png.name, "sha256": digest(png),
            "extent": [-40, -85, 690, 135], "pixels": [1460, 440], "dpi": 96}


def compare(actual, reference, expected=EXPECTED):
    left, right = actual["labels"], reference["labels"]
    visible = {key for key, values in expected.items() if values[6]}
    require(set(left) == visible, f"Native visible keys {sorted(left)} != {sorted(visible)}")
    require(set(right) == visible, f"Oracle visible keys {sorted(right)} != {sorted(visible)}")
    comparisons = {}
    for key in sorted(visible):
        require(left[key]["text"] == right[key]["text"] == expected[key][2], f"{key}: wrong native label text")
        if expected[key][7] == "auto":
            require(not left[key]["pinned"] and not right[key]["pinned"], f"{key}: automatic label pinned")
            comparisons[key] = {"mode": "automatic", "visible": True,
                                "exact_collision_placement_compared": False}
            continue
        require(left[key]["pinned"] and right[key]["pinned"], f"{key}: explicit label position not pinned")
        a, b = left[key]["corners"], right[key]["corners"]
        require(len(a) == len(b), f"{key}: bounding polygons differ")
        distance = max(max(min(math.dist(p, q) for q in b) for p in a),
                       max(min(math.dist(p, q) for q in a) for p in b))
        require(distance <= TOLERANCE, f"{key}: native polygon differs from independent oracle by {distance}")
        for property_name in ("rotation", "width", "height"):
            equal_number(left[key][property_name], right[key][property_name], f"{key}.{property_name}")
        # Base fixture uses 0 degrees and the native default left/bottom anchor.
        if expected[key][5] == 0:
            equal_number(min(p[0] for p in a), expected[key][3], f"{key}.rendered_anchor.x")
            equal_number(min(p[1] for p in a), expected[key][4], f"{key}.rendered_anchor.y")
        comparisons[key] = {"mode": "pinned", "max_corner_distance": distance,
                            "position_and_polygon_match": True}
    return comparisons


def read_project(path):
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import QUrl
    project = QgsProject()
    require(project.read(str(path)), f"QgsProject.read failed: {path.name}")
    layers = list(project.mapLayers().values())
    require(len(layers) == 1, f"Expected one project layer, found {len(layers)}")
    layer = layers[0]
    require(layer.providerType() == "delimitedtext", f"Unexpected provider {layer.providerType()}")
    local_source = Path(QUrl(layer.source()).toLocalFile()).resolve()
    require(local_source == (path.parent / "rebased.csv").resolve(),
            f"Project did not resolve CSV at moved bundle location: {local_source}")
    require(project.crs().authid() == "EPSG:3857", f"Wrong project CRS {project.crs().authid()}")
    return project, layer


def verify(bundle, output, report):
    from qgis.core import QgsVectorLayer
    from qgis.PyQt.QtGui import QFontDatabase
    report["runtime"] = runtime_info()
    require("DejaVu Sans" in QFontDatabase().families(), "Runner must install DejaVu Sans; no fallback-font pass")
    csv_rows = check_serialized_contract(bundle)
    report["inputs"] = {name: {"sha256": digest(bundle / name), "bytes": (bundle / name).stat().st_size}
                        for name in FILES}
    report["checks"].append("actual exporter bundle and typed-string CSVT inspected")
    with tempfile.TemporaryDirectory(prefix="labelrebase-native-") as scratch:
        root = Path(scratch)
        original = root / "before"
        original.mkdir()
        for name in FILES:
            shutil.copy2(bundle / name, original / name)
        moved = root / "relocated bundle with spaces"
        shutil.move(str(original), moved)
        require(not original.exists(), "Relocation did not remove former folder")
        # Working directory is deliberately outside the bundle.
        before_cwd = Path.cwd()
        os.chdir(root)
        try:
            project, layer = read_project(moved / "rebased.qgs")
            report["imported"] = check_layer(layer)
            report["checks"].append("QgsProject.read + valid layer after real folder move and unrelated cwd")
            report["checks"].append("native fields, geometry, exact keys 007/7, A follow, B keep, C/N null, D hidden, E absent")
            oracle = independent_layer()
            check_layer(oracle)
            reference = render(oracle, output, "independent-reference")
            actual = render(layer, output, "relocated-project")
            report["renders"] = {"independent": reference, "project": actual}
            report["comparisons"] = {"project": compare(actual, reference)}
            report["checks"].append("pinned label polygons/positions match independent native memory layer; C/N automatic and D absent")

            standalone = QgsVectorLayer(layer.source(), "Standalone exported QML", "delimitedtext")
            message, success = standalone.loadNamedStyle(str(moved / "rebased.qml"))
            require(success, f"Native exported QML load failed: {message}")
            check_layer(standalone)
            standalone_render = render(standalone, output, "standalone-qml")
            report["renders"]["standalone_qml"] = standalone_render
            report["comparisons"]["standalone_qml"] = compare(standalone_render, reference)
            report["checks"].append("separately imported actual QML matches project and independent label geometry")

            # Reuse exact QGS/QML/CSVT bytes and reverse only physical CSV row order.
            reorder = root / "reordered bundle"
            shutil.copytree(moved, reorder)
            write_csv(reorder / "rebased.csv", list(reversed(csv_rows)))
            reordered_project, reordered_layer = read_project(reorder / "rebased.qgs")
            reordered_values = check_layer(reordered_layer)
            first_fids = report["imported"]["provider_fids"]
            next_fids = reordered_values["provider_fids"]
            changed = sorted(key for key in EXPECTED if first_fids[key] != next_fids[key])
            require(len(changed) >= 2, "Physical row reversal did not change native provider FIDs")
            reordered_render = render(reordered_layer, output, "reordered-provider-fids")
            report["renders"]["reordered"] = reordered_render
            report["comparisons"]["reordered"] = compare(reordered_render, reference)
            report["provider_fid_reordering"] = {"before": first_fids, "after": next_fids,
                                                  "changed_keys": changed, "stable_key_labels_unchanged": True}
            report["checks"].append("provider FIDs really change under CSV reversal; stable-key values and pinned polygons do not")

            # All main-fixture keys include letters, so CSV inference alone could
            # accidentally look correct. A numeric-looking-only subset tests the
            # actual CSVT String contract with the *unchanged* QGS/QML/CSVT bytes.
            numeric = root / "numeric-looking keys only"
            shutil.copytree(moved, numeric)
            numeric_rows = [row for row in csv_rows if row["stable_key"] in ("007", "7")]
            write_csv(numeric / "rebased.csv", numeric_rows)
            numeric_expected = {key: EXPECTED[key] for key in ("007", "7")}
            numeric_project, numeric_layer = read_project(numeric / "rebased.qgs")
            numeric_values = check_layer(numeric_layer, numeric_expected)
            numeric_render = render(numeric_layer, output, "numeric-only-string-keys")
            numeric_reference = {**reference, "labels": {
                key: reference["labels"][key] for key in numeric_expected
            }}
            report["renders"]["numeric_only_keys"] = numeric_render
            report["comparisons"]["numeric_only_keys"] = compare(
                numeric_render, numeric_reference, numeric_expected)
            report["numeric_only_string_key_control"] = {
                "keys": list(numeric_values["rows"]),
                "provider_fids": numeric_values["provider_fids"],
                "native_type": "String",
                "distinct_exact_strings_preserved": True,
                "unchanged_supporting_file_hashes": {
                    name: digest(numeric / name) for name in FILES if name != "rebased.csv"
                },
            }
            report["checks"].append("numeric-looking-only CSV subset preserves distinct String keys 007/7 through actual CSVT")

            # Native positive controls, explicitly distinguished from exporter outputs:
            # make hidden D visible and rotate B 25 degrees in temporary CSV copies.
            control = root / "visibility rotation controls"
            shutil.copytree(moved, control)
            controls = [dict(row) for row in csv_rows]
            for row in controls:
                if row["stable_key"] == "D":
                    row["label_show"] = "1"
                if row["stable_key"] == "B":
                    row["label_rotation"] = "25"
            write_csv(control / "rebased.csv", controls)
            expected_control = dict(EXPECTED)
            expected_control["D"] = (330, 0, "Hidden", 342, 8, 0, 1, "pinned")
            expected_control["B"] = (120, 10, "Bravo", 112, 8, 25, 1, "pinned")
            control_project, control_layer = read_project(control / "rebased.qgs")
            check_layer(control_layer, expected_control)
            control_oracle = independent_layer(expected_control)
            control_reference = render(control_oracle, output, "control-independent-reference")
            control_actual = render(control_layer, output, "control-visible-d-rotated-b")
            report["renders"]["control_reference"] = control_reference
            report["renders"]["control_project"] = control_actual
            report["comparisons"]["native_binding_controls"] = compare(control_actual, control_reference, expected_control)
            require("D" not in actual["labels"] and "D" in control_actual["labels"],
                    "Show field control did not change D's rendered visibility")
            require(abs(control_actual["labels"]["B"]["rotation"] - actual["labels"]["B"]["rotation"]) > 1e-6,
                    "Rotation field control did not change B's rendered rotation")
            report["checks"].append("native positive controls: D becomes visible and B rotates with unchanged exported style")
            # QGIS layer ownership is explicitly released before temp files disappear.
            project.clear()
            reordered_project.clear()
            numeric_project.clear()
            control_project.clear()
        finally:
            os.chdir(before_cwd)
    report["passed"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("artifacts/demo"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/native"))
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "passed": False, "checked_at": datetime.now(timezone.utc).isoformat(),
              "checks": [], "scope": "EPSG:3857 single-line point labels; generated minimal style, no original-style preservation",
              "comparison_tolerance_map_units": TOLERANCE,
              "automatic_label_collision_positions_are_not_exactly_compared": True}
    application = None
    try:
        from qgis.core import QgsApplication
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
        application = QgsApplication([], False)
        application.initQgis()
        verify(bundle, output, report)
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    finally:
        (output / "native-result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "checks": report["checks"], "error": report.get("error"),
                          "report": str(output / "native-result.json")}, indent=2))
        if application is not None:
            import gc
            gc.collect()
            application.exitQgis()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
