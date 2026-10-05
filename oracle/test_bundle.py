"""Prove the verifier rejects corruption, rather than accepting every export."""
from __future__ import annotations
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bundle_verifier", ROOT / "scripts/verify-bundle.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class BundleVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix="labelrebase-oracle-")
        cls.clean = Path(cls.storage.name) / "clean"
        process = subprocess.run(["node", "scripts/export-demo.mjs", str(cls.clean)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        if process.returncode:
            raise AssertionError(f"Demo export failed: {process.stdout}\n{process.stderr}")
        verifier.verify_bundle(cls.clean)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.storage_case = tempfile.TemporaryDirectory(prefix="labelrebase-mutation-")
        self.directory = Path(self.storage_case.name) / "bundle"
        shutil.copytree(self.clean, self.directory)

    def tearDown(self):
        self.storage_case.cleanup()

    def mutate_text(self, filename, before, after):
        path = self.directory / filename
        text = path.read_text()
        self.assertIn(before, text)
        path.write_text(text.replace(before, after, 1))

    def mutate_json(self, filename, change):
        path = self.directory / filename
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def assert_rejected(self, semantic_reason):
        # A stale ZIP cannot masquerade as detection of an earlier semantic flaw.
        # Every mutation must fail for its specific intended reason.
        with self.assertRaisesRegex(AssertionError, re.escape(semantic_reason)):
            verifier.verify_bundle(self.directory)

    def test_valid_export_passes(self):
        self.assertTrue(verifier.verify_bundle(self.directory)["ok"])

    def test_adversarial_unicode_quotes_xml_chars_export_roundtrip(self):
        from oracle.reference import csv_text, read_csv
        request = json.loads((ROOT / "oracle/fixtures/canonical.json").read_text())
        special_key = "<&\"'東京"
        for side in ["old", "new"]:
            rows = read_csv(request[side + "CSV"])
            for row in rows:
                if row["key"] == "A": row["key"] = special_key
                if side == "new" and row["key"] == "N": row["text"] = '<tag>&"quote", 東京 🗺'
            header = list(rows[0])
            request[side + "CSV"] = csv_text(header, [[row[field] for field in header] for row in rows])
        request["decisions"][special_key] = request["decisions"].pop("A")
        request_path = Path(self.storage_case.name) / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False))
        output = Path(self.storage_case.name) / "roundtrip 日本"
        process = subprocess.run(["node", "scripts/export-demo.mjs", str(output), str(request_path)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(verifier.verify_bundle(output, request_path)["ok"])

    def test_30_place_precision_epsg3395_aliases_export_roundtrip(self):
        request_path = ROOT / "oracle/fixtures/precision-boundary.json"
        output = Path(self.storage_case.name) / "precision-boundary"
        process = subprocess.run(["node", "scripts/export-demo.mjs", str(output), str(request_path)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(verifier.verify_bundle(output, request_path)["ok"])
        golden = verifier.read_csv((ROOT / "oracle/fixtures/precision-boundary-expected.csv").read_text())
        actual = verifier.read_csv((output / "rebased.csv").read_text())
        verifier.assert_rows(actual, golden)

    def test_partial_mapping_export_roundtrip(self):
        from oracle.reference import csv_text, read_csv
        request = json.loads((ROOT / "oracle/fixtures/canonical.json").read_text())
        for side, old_name, new_name, role in [("old", "key", "business_id", "key"), ("new", "text", "caption", "text")]:
            rows = read_csv(request[side + "CSV"])
            header = list(rows[0])
            request[side + "CSV"] = csv_text([new_name if field == old_name else field for field in header], [[row[field] for field in header] for row in rows])
            request[side + "Mapping"] = {role: new_name}
        request_path = Path(self.storage_case.name) / "partial-mapping.json"
        request_path.write_text(json.dumps(request))
        output = Path(self.storage_case.name) / "partial-mapping"
        process = subprocess.run(["node", "scripts/export-demo.mjs", str(output), str(request_path)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(verifier.verify_bundle(output, request_path)["ok"])

    def test_missing_file_rejected(self):
        (self.directory / "rebased.csvt").unlink()
        self.assert_rejected('Missing bundle member: rebased.csvt')

    def test_wrong_follow_offset_rejected(self):
        self.mutate_text("rebased.csv", ",22,28,", ",23,28,")
        self.assert_rejected('A/label_x:')

    def test_coerced_leading_zero_key_rejected(self):
        self.mutate_text("rebased.csv", "007,500", "7,500")
        self.assert_rejected('Output contains duplicate stable keys')

    def test_key_numeric_type_rejected(self):
        self.mutate_text("rebased.csvt", '"String"', '"Integer"')
        self.assert_rejected('CSVT must retain key/text strings and numeric field types')

    def test_qml_wrong_position_binding_rejected(self):
        self.mutate_text("rebased.qml", 'value="label_x"', 'value="point_x"')
        self.assert_rejected('QML: PositionX must reference label_x')

    def test_qml_inactive_binding_rejected(self):
        self.mutate_text("rebased.qml", 'name="active" type="bool" value="true"', 'name="active" type="bool" value="false"')
        self.assert_rejected('QML: inactive PositionX binding')

    def test_qgs_absolute_datasource_rejected(self):
        self.mutate_text("rebased.qgs", "file:./rebased.csv", "file:/tmp/rebased.csv")
        self.assert_rejected('Datasource must use bundle-relative rebased.csv')

    def test_qgs_crs_mismatch_rejected(self):
        self.mutate_text("rebased.qgs", "EPSG:3857", "EPSG:4326")
        self.assert_rejected('QGS CRS differs from input')

    def test_qgs_hidden_binding_corruption_rejected(self):
        self.mutate_text("rebased.qgs", 'value="label_show"', 'value="label_state"')
        self.assert_rejected('QGS: Show must reference label_show')

    def test_source_hash_corruption_rejected(self):
        self.mutate_json("decisions.json", lambda data: data["sourceHashes"].update(old="0" * 64))
        self.assert_rejected('Old-source SHA256 mismatch')

    def test_removed_receipt_corruption_rejected(self):
        self.mutate_json("decisions.json", lambda data: data.update(removedKeys=[]))
        self.assert_rejected('Removed-key receipt mismatch')

    def test_choice_receipt_corruption_rejected(self):
        self.mutate_json("decisions.json", lambda data: data["decisions"].update(A="keep"))
        self.assert_rejected('Receipt decisions differ from applied choices')

    def test_duplicate_receipt_json_key_rejected(self):
        self.mutate_text("decisions.json", '"version": 1', '"version": 1, "version": 1')
        self.assert_rejected('Duplicate JSON member: version')

    def test_saved_project_source_corruption_rejected(self):
        self.mutate_json("labelrebase-project.json", lambda data: data["input"].update(newCSV=data["input"]["newCSV"].replace("Alpha", "Changed")))
        self.assert_rejected('Saved project changes source input: newCSV')

    def test_zip_stale_member_rejected(self):
        path = next(self.directory.glob("*.zip"))
        with ZipFile(path) as archive:
            entries = {item: archive.read(item) for item in archive.namelist()}
        entries["README.txt"] += b"tampered"
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for name, content in entries.items(): archive.writestr(name, content)
        self.assert_rejected('ZIP README.txt differs from exported file')

    def test_zip_path_traversal_rejected(self):
        path = next(self.directory.glob("*.zip"))
        with ZipFile(path, "a") as archive:
            archive.writestr("../escape.txt", "outside")
        self.assert_rejected('Unsafe ZIP path')


if __name__ == "__main__":
    unittest.main()
