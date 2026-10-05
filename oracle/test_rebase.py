"""Black-box adversarial and metamorphic tests with a separate Decimal oracle.

Run: python3 -m unittest discover -s oracle -p 'test_*.py' -v
No application modules are imported or inspected by these tests.
"""
from __future__ import annotations
import copy
import csv
import io
import json
import random
import subprocess
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

try:
    from reference import OLD_MAPPING, NEW_MAPPING, assert_rows, csv_text, expected_rows, read_csv
except ImportError:
    from oracle.reference import OLD_MAPPING, NEW_MAPPING, assert_rows, csv_text, expected_rows, read_csv

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "oracle/fixtures/canonical.json"


def baseline():
    return json.loads(FIXTURE.read_text())


def records(raw):
    return list(csv.reader(io.StringIO(raw, newline="")))


def edit_cell(request, side, row_key, field, value):
    matrix = records(request[side + "CSV"])
    index = matrix[0].index(field)
    key_col = matrix[0].index("key")
    for row in matrix[1:]:
        if row[key_col] == row_key:
            row[index] = value
    request[side + "CSV"] = csv_text(matrix[0], matrix[1:])


def invoke(request):
    execution = subprocess.run(["node", "scripts/solve-json.mjs"], cwd=ROOT, input=json.dumps(request, ensure_ascii=False), text=True, capture_output=True, timeout=20)
    try:
        response = json.loads(execution.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f"CLI did not return JSON (exit {execution.returncode}): {execution.stdout!r}, stderr={execution.stderr!r}") from error
    if execution.returncode and response.get("ok") is not False:
        raise AssertionError(f"Unexpected CLI exit: {execution.returncode}: {execution.stderr}")
    return response


class IndependentRebaseTests(unittest.TestCase):
    def assert_success(self, request):
        result = invoke(request)
        self.assertTrue(result.get("ok"), result)
        assert_rows(result["rows"], expected_rows(request))
        return result["rows"]

    def assert_blocked(self, request):
        result = invoke(request)
        self.assertIs(result.get("ok"), False, result)
        self.assertTrue(result.get("errors"), result)
        # Fail closed: invalid input must not advertise successful output rows.
        self.assertFalse(result.get("rows"), result)

    def test_handwritten_canonical_golden(self):
        expected = read_csv((ROOT / "oracle/fixtures/canonical-expected.csv").read_text())
        # Cross-check the independently implemented oracle against handwritten math.
        assert_rows(expected_rows(baseline()), expected)
        actual = self.assert_success(baseline())
        assert_rows(actual, expected)

    def test_reset_clears_position_and_rotation_preserves_hidden(self):
        request = baseline()
        request["decisions"]["D"] = "reset"
        rows = self.assert_success(request)
        hidden = next(row for row in rows if row["stable_key"] == "D")
        self.assertEqual(str(hidden["label_show"]), "0")
        self.assertEqual(hidden["label_state"], "auto")
        self.assertEqual(Decimal(str(hidden["label_rotation"])), 0)

    def test_all_moved_pinned_need_an_explicit_decision_including_hidden(self):
        for key in ["A", "B", "D", "007", "7"]:
            with self.subTest(key=key):
                request = baseline()
                del request["decisions"][key]
                self.assert_blocked(request)

    def test_invalid_decisions_block(self):
        for choice in ["", "automatic", "FOLLOW", 0, None, True]:
            with self.subTest(choice=choice):
                request = baseline()
                request["decisions"]["A"] = choice
                self.assert_blocked(request)

    def test_auto_and_unmoved_do_not_need_decisions(self):
        request = baseline()
        edit_cell(request, "new", "A", "x", "0")
        edit_cell(request, "new", "A", "y", "0")
        del request["decisions"]["A"]
        self.assert_success(request)

    def test_automatic_label_rotation_preserved(self):
        request = baseline()
        edit_cell(request, "old", "C", "rotation", "42.5")
        self.assert_success(request)

    def test_equivalent_decimal_forms_are_unmoved(self):
        request = baseline()
        edit_cell(request, "old", "A", "x", "1e1")
        edit_cell(request, "old", "A", "y", "2.00e1")
        del request["decisions"]["A"]
        self.assert_success(request)

    def test_removed_and_new_key_receipt_population(self):
        actual = self.assert_success(baseline())
        keys = {row["stable_key"] for row in actual}
        self.assertNotIn("E", keys)
        added = next(row for row in actual if row["stable_key"] == "N")
        self.assertEqual(added["label_state"], "auto")

    def test_exact_keys_and_proto_names(self):
        request = baseline()
        for side in ["old", "new"]:
            matrix = records(request[side + "CSV"])
            for row in matrix[1:]:
                if row[0] == "A": row[0] = "__proto__"
                if row[0] == "B": row[0] = "constructor"
                if row[0] == "007": row[0] = " 007 "
            request[side + "CSV"] = csv_text(matrix[0], matrix[1:])
        request["decisions"] = {"__proto__": "follow", "constructor": "keep", "D": "follow", " 007 ": "follow", "7": "keep"}
        self.assert_success(request)

    def test_duplicate_keys_both_sources_block(self):
        for side in ["old", "new"]:
            with self.subTest(side=side):
                request = baseline()
                matrix = records(request[side + "CSV"])
                matrix.append(matrix[1].copy())
                request[side + "CSV"] = csv_text(matrix[0], matrix[1:])
                self.assert_blocked(request)

    def test_duplicate_headers_both_sources_block(self):
        for side in ["old", "new"]:
            with self.subTest(side=side):
                request = baseline()
                matrix = records(request[side + "CSV"])
                matrix[0][-1] = "key"
                request[side + "CSV"] = csv_text(matrix[0], matrix[1:])
                self.assert_blocked(request)

    def test_empty_keys_block(self):
        for side in ["old", "new"]:
            for value in ["", " ", "\t"]:
                with self.subTest(side=side, value=value):
                    request = baseline()
                    edit_cell(request, side, "A", "key", value)
                    self.assert_blocked(request)

    def test_nonfinite_and_malformed_point_coordinates_block(self):
        for side in ["old", "new"]:
            for field in ["x", "y"]:
                for value in ["", "NaN", "Infinity", "-Infinity", "1e9999", "0x10", "12oops", "1,000"]:
                    with self.subTest(side=side, field=field, value=value):
                        request = baseline()
                        edit_cell(request, side, "A", field, value)
                        self.assert_blocked(request)

    def test_half_blank_or_nonfinite_labels_block(self):
        for field in ["label_x", "label_y"]:
            for value in ["", "NaN", "Infinity", "bad"]:
                with self.subTest(field=field, value=value):
                    request = baseline()
                    edit_cell(request, "old", "A", field, value)
                    self.assert_blocked(request)

    def test_nonfinite_rotation_or_invalid_show_block(self):
        for field, values in [("rotation", ["NaN", "Infinity", "no"]), ("show", ["2", "maybe", "-1"])]:
            for value in values:
                with self.subTest(field=field, value=value):
                    request = baseline()
                    edit_cell(request, "old", "A", field, value)
                    self.assert_blocked(request)

    def test_mismatched_geographic_and_unsupported_crs_block(self):
        pairs = [("EPSG:3857", "EPSG:32654"), ("EPSG:4326", "EPSG:4326"), ("", ""), ("EPSG:32600", "EPSG:32600"), ("EPSG:32661", "EPSG:32661"), ("EPSG:32700", "EPSG:32700"), ("EPSG:32761", "EPSG:32761"), ("EPSG:999999", "EPSG:999999")]
        for old, new in pairs:
            with self.subTest(old=old, new=new):
                request = baseline()
                request.update(oldCRS=old, newCRS=new)
                self.assert_blocked(request)

    def test_supported_projected_crs_boundaries(self):
        for crs in ["EPSG:3857", "EPSG:3395", "EPSG:32601", "EPSG:32660", "EPSG:32701", "EPSG:32760"]:
            with self.subTest(crs=crs):
                request = baseline()
                request.update(oldCRS=crs, newCRS=crs)
                self.assert_success(request)

    def test_exact_decimal_offset_arithmetic(self):
        request = {"oldCSV": csv_text(["key", "x", "y", "label_x", "label_y", "rotation", "show"], [["decimal", "0.1", "-0.1", "0.2", "0.2", "-12.5", "1"], ["precision", "99999.999999999", "0.000000001", "100000.000000001", "0.000000003", "0", "0"]]), "newCSV": csv_text(["key", "x", "y", "text"], [["decimal", "0.2", "0.1", "Decimals"], ["precision", "100000.000000001", "0.000000003", "Precision"]]), "oldCRS": "EPSG:3857", "newCRS": "EPSG:3857", "decisions": {"decimal": "follow", "precision": "follow"}}
        self.assert_success(request)

    def test_29_and_30_decimal_place_follow_offsets_match_handwritten_results(self):
        request = json.loads((ROOT / "oracle/fixtures/precision-boundary.json").read_text())
        golden = read_csv((ROOT / "oracle/fixtures/precision-boundary-expected.csv").read_text())
        # The oracle must remain exact even when called from the default context.
        with localcontext() as context:
            context.prec = 28
            assert_rows(expected_rows(request), golden)
            actual = self.assert_success(request)
            assert_rows(actual, golden)
        for row in golden:
            with self.subTest(key=row["stable_key"]):
                got = next(actual_row for actual_row in actual if actual_row["stable_key"] == row["stable_key"])
                self.assertEqual(Decimal(got["label_x"]), Decimal(row["label_x"]))
                self.assertEqual(Decimal(got["label_y"]), Decimal(row["label_y"]))

    def test_visibility_aliases_normalize_across_keep_follow_reset_and_auto(self):
        for alias, expected in [("", "1"), ("0", "0"), ("1", "1"), ("true", "1"), ("false", "0"), ("TRUE", "1"), ("FALSE", "0")]:
            with self.subTest(alias=alias):
                request = baseline()
                for key in ["A", "B", "C", "D"]:
                    edit_cell(request, "old", key, "show", alias)
                request["decisions"]["D"] = "reset"
                rows = self.assert_success(request)
                for row in rows:
                    if row["stable_key"] in ["A", "B", "C", "D"]:
                        self.assertEqual(str(row["label_show"]), expected)

    def test_leading_zero_epsg_codes_blocked(self):
        for crs in ["EPSG:03857", "EPSG:003395", "EPSG:032654", "EPSG:0032760"]:
            with self.subTest(crs=crs):
                request = baseline()
                request.update(oldCRS=crs, newCRS=crs)
                self.assert_blocked(request)

    def test_extreme_scale_cancellation_and_carry_stay_exact(self):
        tiny = "0." + "0" * 29 + "1"
        request = {
            "oldCSV": csv_text(["key", "x", "y", "label_x", "label_y", "rotation", "show"], [
                ["cancel", "1000000000000", "0", "1000000000000", "0", "0", "1"],
                ["carry", "0", "0", "0." + "9" * 30, "0", "0", "1"],
            ]),
            "newCSV": csv_text(["key", "x", "y", "text"], [
                ["cancel", tiny, "0", "Large coordinate cancellation"],
                ["carry", tiny, "0", "Decimal carry"],
            ]),
            "oldCRS": "EPSG:3857", "newCRS": "EPSG:3857",
            "decisions": {"cancel": "follow", "carry": "follow"},
        }
        actual = {row["stable_key"]: row for row in self.assert_success(request)}
        self.assertEqual(Decimal(actual["cancel"]["label_x"]), Decimal(tiny))
        self.assertEqual(Decimal(actual["carry"]["label_x"]), Decimal("1"))

    def test_partial_mappings_merge_documented_defaults(self):
        request = baseline()
        old_matrix = records(request["oldCSV"])
        old_matrix[0][old_matrix[0].index("key")] = "business_id"
        request["oldCSV"] = csv_text(old_matrix[0], old_matrix[1:])
        new_matrix = records(request["newCSV"])
        new_matrix[0][new_matrix[0].index("text")] = "caption"
        request["newCSV"] = csv_text(new_matrix[0], new_matrix[1:])
        request["oldMapping"] = {"key": "business_id"}
        request["newMapping"] = {"text": "caption"}
        self.assert_success(request)
        # Explicitly empty optional overrides also retain the other defaults.
        request["oldMapping"]["show"] = ""
        self.assert_success(request)

    def test_custom_field_mapping_and_optional_fields(self):
        request = baseline()
        names = {"key": "business_id", "x": "east", "y": "north", "label_x": "anchor_x", "label_y": "anchor_y", "rotation": "angle", "show": "visible", "text": "caption"}
        for side in ["old", "new"]:
            matrix = records(request[side + "CSV"])
            request[side + "CSV"] = csv_text([names.get(header, header) for header in matrix[0]], matrix[1:])
            defaults = OLD_MAPPING if side == "old" else NEW_MAPPING
            request[side + "Mapping"] = {role: names[column] for role, column in defaults.items()}
        request["oldMapping"].update(rotation="", show="")
        self.assert_success(request)

    def test_missing_mapping_column_blocks(self):
        for side, defaults in [("old", OLD_MAPPING), ("new", NEW_MAPPING)]:
            for role in defaults:
                with self.subTest(side=side, role=role):
                    request = baseline()
                    request[side + "Mapping"] = {**defaults, role: "does_not_exist"}
                    self.assert_blocked(request)

    def test_bom_crlf_unicode_quotes_commas_preserved(self):
        request = baseline()
        for side in ["old", "new"]:
            matrix = records(request[side + "CSV"])
            request[side + "CSV"] = "\ufeff" + csv_text(matrix[0], matrix[1:], newline="\r\n")
        self.assert_success(request)

    def test_multiline_and_blank_text_blocked_by_v1_scope(self):
        for value in ["", " ", "New\nline", "New\rline"]:
            with self.subTest(value=value):
                request = baseline()
                edit_cell(request, "new", "N", "text", value)
                self.assert_blocked(request)

    def test_row_permutation_is_semantically_irrelevant(self):
        expected = self.assert_success(baseline())
        for seed in range(8):
            with self.subTest(seed=seed):
                request = baseline()
                for side in ["old", "new"]:
                    matrix = records(request[side + "CSV"])
                    data = matrix[1:]
                    random.Random(seed + (100 if side == "new" else 0)).shuffle(data)
                    request[side + "CSV"] = csv_text(matrix[0], data)
                assert_rows(self.assert_success(request), expected)

    def test_regenerated_and_duplicate_fids_are_irrelevant(self):
        expected = self.assert_success(baseline())
        request = baseline()
        for side in ["old", "new"]:
            matrix = records(request[side + "CSV"])
            index = matrix[0].index("fid")
            for row in matrix[1:]: row[index] = "1"
            request[side + "CSV"] = csv_text(matrix[0], matrix[1:])
        assert_rows(self.assert_success(request), expected)

    def test_global_translation_preserves_offset_and_decision_semantics(self):
        before = self.assert_success(baseline())
        for dx, dy in [(Decimal("200000.5"), Decimal("-5000.125")), (Decimal("-1"), Decimal("3"))]:
            with self.subTest(dx=dx, dy=dy):
                request = baseline()
                for side in ["old", "new"]:
                    matrix = records(request[side + "CSV"])
                    for row in matrix[1:]:
                        for field, offset in [("x", dx), ("y", dy), ("label_x", dx), ("label_y", dy)]:
                            if field in matrix[0]:
                                i = matrix[0].index(field)
                                if row[i] != "": row[i] = str(Decimal(row[i]) + offset)
                    request[side + "CSV"] = csv_text(matrix[0], matrix[1:])
                translated = self.assert_success(request)
                undo = copy.deepcopy(translated)
                for row in undo:
                    for field, offset in [("point_x", dx), ("point_y", dy), ("label_x", dx), ("label_y", dy)]:
                        if row[field] not in (None, ""): row[field] = str(Decimal(str(row[field])) - offset)
                assert_rows(undo, before)

    def test_malformed_csv_row_width_and_quoting_block(self):
        for side in ["old", "new"]:
            for suffix in ["broken\n", '"unterminated\n', "too,many,columns,for,one,record,here,extra,extra,extra\n"]:
                with self.subTest(side=side, suffix=suffix):
                    request = baseline()
                    request[side + "CSV"] += suffix
                    self.assert_blocked(request)


if __name__ == "__main__":
    unittest.main()
