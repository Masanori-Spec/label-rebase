#!/usr/bin/env python3
"""Verify exported CSV/QML/QGS/JSON/ZIP using independent Python parsers.

Usage: python3 scripts/verify-bundle.py artifacts/demo [--input request.json]
This structural/semantic verifier is not a substitute for native QGIS rendering.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oracle.reference import COLUMNS, assert_rows, expected_rows, keyed, mapping_for, read_csv, source_hash

REQUIRED = {"rebased.csv", "rebased.csvt", "rebased.qml", "rebased.qgs", "decisions.json", "labelrebase-project.json", "README.txt"}
CSV_TYPES = ["String", "Real", "Real", "String", "Real", "Real", "Real", "Integer", "String"]
PROPERTY_FIELDS = {"PositionX": "label_x", "PositionY": "label_y", "LabelRotation": "label_rotation", "Show": "label_show"}


def load_json(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, f"Duplicate JSON member: {key}"
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def load_xml(path):
    raw = path.read_text(encoding="utf-8")
    assert "<!ENTITY" not in raw.upper(), f"XML entity declaration is not allowed: {path.name}"
    return ET.fromstring(raw)


def check_labeling(node, name):
    labeling = node.findall("labeling")
    assert len(labeling) == 1 and labeling[0].get("type") == "simple", f"{name}: single simple labeler required"
    settings = labeling[0].find("settings")
    assert settings is not None, f"{name}: missing label settings"
    text = settings.find("text-style")
    assert text is not None and text.get("fieldName") == "label_text" and text.get("isExpression") == "0", f"{name}: label_text must be a field"
    props = settings.findall("dd_properties/Option/Option[@name='properties']/Option")
    by_name = {prop.get("name"): prop for prop in props}
    assert len(by_name) == len(props), f"{name}: duplicate label properties"
    for role, field in PROPERTY_FIELDS.items():
        assert role in by_name, f"{name}: missing {role} binding"
        options = by_name[role].findall("Option")
        values = {option.get("name"): option.get("value") for option in options}
        assert len(values) == len(options), f"{name}: duplicate {role} property options"
        assert values.get("active") == "true", f"{name}: inactive {role} binding"
        assert values.get("type") == "2", f"{name}: {role} must be a field property"
        assert values.get("field") == field, f"{name}: {role} must reference {field}"
    rendering = settings.find("rendering")
    assert rendering is not None and rendering.get("drawLabels") == "1", f"{name}: labels disabled"


def check_datasource(source, crs):
    parsed = urlsplit(source)
    assert parsed.scheme in ("", "file") and not parsed.netloc, "Datasource must be a local CSV"
    assert parsed.path in ("./rebased.csv", "rebased.csv"), "Datasource must use bundle-relative rebased.csv"
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, expected in [("type", "csv"), ("xField", "point_x"), ("yField", "point_y"), ("crs", crs)]:
        assert query.get(key) == [expected], f"Datasource {key} mismatch: {query.get(key)}"


def verify_bundle(directory, input_path=None):
    directory = Path(directory)
    for filename in REQUIRED:
        assert (directory / filename).is_file(), f"Missing bundle member: {filename}"
    project = load_json(directory / "labelrebase-project.json")
    assert project.get("format") == "label-rebase-project" and project.get("version") == 1, "Invalid project format/version"
    project_request = {**project["input"], "decisions": project["decisions"]}
    path = Path(input_path) if input_path else directory / "input.json"
    request = load_json(path) if path.is_file() else project_request
    for key in ["oldCSV", "newCSV", "oldCRS", "newCRS"]:
        assert project_request.get(key) == request.get(key), f"Saved project changes source input: {key}"
    for side in ["old", "new"]:
        assert mapping_for(project_request, side) == mapping_for(request, side), f"Saved project changes {side}Mapping"
    expected = expected_rows(request)
    assert_rows(expected_rows(project_request), expected)

    raw_csv = (directory / "rebased.csv").read_text(encoding="utf-8")
    headers = next(csv.reader(io.StringIO(raw_csv, newline="")))
    assert headers == COLUMNS, "Output CSV field order/schema differs"
    actual = read_csv(raw_csv)
    assert_rows(actual, expected)
    # Unlike the internal object representation, exported CSV auto coordinates must be empty.
    for row in actual:
        if row["label_state"] == "auto":
            assert row["label_x"] == row["label_y"] == "", "Auto CSV coordinates must be empty"
    type_rows = list(csv.reader(io.StringIO((directory / "rebased.csvt").read_text())))
    assert type_rows == [CSV_TYPES], "CSVT must retain key/text strings and numeric field types"

    receipt = load_json(directory / "decisions.json")
    assert receipt.get("format") == "label-rebase-decisions" and receipt.get("version") == 1, "Invalid receipt format/version"
    assert receipt.get("crs") == request["oldCRS"], "Receipt CRS mismatch"
    hashes = receipt.get("sourceHashes", {})
    assert hashes.get("old") == source_hash(request["oldCSV"]), "Old-source SHA256 mismatch"
    assert hashes.get("new") == source_hash(request["newCSV"]), "New-source SHA256 mismatch"
    old_mapping, new_mapping = mapping_for(request, "old"), mapping_for(request, "new")
    assert receipt.get("oldMapping") == old_mapping and receipt.get("newMapping") == new_mapping, "Receipt mapping mismatch"
    old = keyed(request["oldCSV"], old_mapping, True)
    new = keyed(request["newCSV"], new_mapping, False)
    removed, added = set(old) - set(new), set(new) - set(old)
    assert len(receipt.get("removedKeys", [])) == len(removed) and set(receipt["removedKeys"]) == removed, "Removed-key receipt mismatch"
    assert len(receipt.get("newKeys", [])) == len(added) and set(receipt["newKeys"]) == added, "New-key receipt mismatch"
    assert receipt.get("counts") == {"old": len(old), "new": len(new), "removed": len(removed), "added": len(added)}, "Receipt counts mismatch"
    required_decisions = {}
    for key, row in new.items():
        previous = old.get(key)
        if previous and previous["label"] and (row["x"], row["y"]) != (previous["x"], previous["y"]):
            required_decisions[key] = request["decisions"][key]
    assert receipt.get("decisions") == required_decisions, "Receipt decisions differ from applied choices"
    assert project.get("decisions") == required_decisions, "Saved project decisions differ from applied choices"
    receipt_rows = receipt.get("rows", [])
    assert len(receipt_rows) == len(new), "Receipt per-key row count mismatch"
    by_key = {row["key"]: row for row in receipt_rows}
    assert len(by_key) == len(new) and set(by_key) == set(new), "Receipt per-key rows are duplicated or incomplete"
    for row in expected:
        key = row["stable_key"]
        decision = "new" if key in added else required_decisions.get(key, "unchanged")
        assert by_key[key].get("decision") == decision, f"Receipt decision mismatch: {key}"
        assert by_key[key].get("labelState") == row["label_state"], f"Receipt label state mismatch: {key}"
        assert by_key[key].get("visible") is (str(row["label_show"]) == "1"), f"Receipt visibility mismatch: {key}"

    qml = load_xml(directory / "rebased.qml")
    assert qml.tag == "qgis" and qml.get("labelsEnabled") == "1", "QML labeling must be enabled"
    check_labeling(qml, "QML")
    qgs = load_xml(directory / "rebased.qgs")
    assert qgs.tag == "qgis", "Invalid QGS root"
    layers = qgs.findall("projectlayers/maplayer")
    assert len(layers) == 1, "QGS must contain exactly one point layer"
    layer = layers[0]
    assert layer.get("type") == "vector" and layer.get("geometry") == "Point", "QGS geometry must be point"
    assert layer.get("labelsEnabled") == "1", "QGS labeling disabled"
    assert layer.findtext("provider") == "delimitedtext", "QGS must use delimitedtext provider"
    check_labeling(layer, "QGS")
    check_datasource(layer.findtext("datasource", ""), request["oldCRS"])
    tree = qgs.findall("layer-tree-group/layer-tree-layer")
    assert len(tree) == 1 and tree[0].get("id") == layer.findtext("id"), "QGS layer-tree mismatch"
    check_datasource(tree[0].get("source", ""), request["oldCRS"])
    assert qgs.findtext("properties/Paths/Absolute") == "false", "QGS relative-path policy absent"
    crs_values = qgs.findall(".//spatialrefsys/authid")
    assert len(crs_values) >= 2 and {node.text for node in crs_values} == {request["oldCRS"]}, "QGS CRS differs from input"

    zips = sorted(directory.glob("*.zip"))
    for path in zips:
        with ZipFile(path) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)), "ZIP duplicate paths"
            for name in names:
                parts = PurePosixPath(name).parts
                assert not name.startswith(("/", "\\")) and ".." not in parts and "\\" not in name, "Unsafe ZIP path"
            assert REQUIRED.issubset(names), "ZIP missing required members"
            assert archive.testzip() is None, "ZIP CRC verification failed"
            for filename in REQUIRED:
                assert archive.read(filename) == (directory / filename).read_bytes(), f"ZIP {filename} differs from exported file"
    return {"ok": True, "rows": len(actual), "removedKeys": sorted(removed), "newKeys": sorted(added), "verified": ["exact Decimal reconciliation", "CSV stable keys/text/types", "QML/QGS bindings", "relative datasource and CRS", "SHA256 source receipts", "saved input and decisions", "ZIP CRC and member equality" if zips else "no ZIP present"], "nativeQGIS": "not evaluated by this structural verifier"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    try:
        result = verify_bundle(args.directory, args.input)
    except (AssertionError, ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
