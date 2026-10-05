"""Independent behavioral specification; imports no application implementation.

Only Python's csv, Decimal, hashlib and XML readers are used. Comparisons require
exact decimal equality; no binary floating-point implementation is reused.
Stable keys, text, visibility, and state are always compared exactly.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from decimal import Context, Decimal, InvalidOperation, localcontext

COLUMNS = ["stable_key", "point_x", "point_y", "label_text", "label_x", "label_y", "label_rotation", "label_show", "label_state"]
OLD_MAPPING = {"key": "key", "x": "x", "y": "y", "labelX": "label_x", "labelY": "label_y", "rotation": "rotation", "show": "show"}
NEW_MAPPING = {"key": "key", "x": "x", "y": "y", "text": "text"}
NUMERIC_COLUMNS = {"point_x", "point_y", "label_x", "label_y", "label_rotation"}
# The input scope permits 30 fractional places and magnitudes up to 1e12.
# 100 significant digits safely covers exact subtraction/addition, with margin.
ORACLE_CONTEXT = Context(prec=100)
NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")


class InvalidInput(ValueError):
    pass


def read_csv(raw: str) -> list[dict[str, str]]:
    """No key coercion, JavaScript parser or dependency on output code."""
    try:
        records = list(csv.reader(io.StringIO(raw.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error as error:
        raise InvalidInput(f"Invalid CSV: {error}") from error
    if not records:
        raise InvalidInput("CSV is empty")
    header = records[0]
    if len(set(header)) != len(header) or any(not item for item in header):
        raise InvalidInput("Duplicate or blank header")
    rows = []
    for record in records[1:]:
        if not record:
            continue
        if len(record) != len(header):
            raise InvalidInput("CSV row width differs from header")
        rows.append(dict(zip(header, record)))
    return rows


def csv_text(header: list[str], records: list[list[object]], newline: str = "\n") -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator=newline)
    writer.writerow(header)
    writer.writerows(records)
    return out.getvalue()


def number(value: object, field: str) -> Decimal:
    raw = str(value).strip()
    if not NUMBER.fullmatch(raw):
        raise InvalidInput(f"{field} is not a finite decimal: {value!r}")
    try:
        result = Decimal(raw)
    except InvalidOperation as error:
        raise InvalidInput(f"{field} is not decimal") from error
    if not result.is_finite():
        raise InvalidInput(f"{field} is not finite")
    return result


def valid_crs(crs: str) -> bool:
    return crs in ("EPSG:3857", "EPSG:3395") or bool(re.fullmatch(r"EPSG:32[67](?:0[1-9]|[1-5][0-9]|60)", crs))


def keyed(raw: str, mapping: dict, old: bool) -> dict:
    rows = read_csv(raw)
    header = next(csv.reader(io.StringIO(raw.lstrip("\ufeff"), newline="")))
    required = ["key", "x", "y", "labelX", "labelY"] if old else ["key", "x", "y", "text"]
    for role in required:
        if not mapping.get(role) or mapping[role] not in header:
            raise InvalidInput(f"Missing mapping column: {role}")
    for role in ("rotation", "show") if old else ():
        if mapping.get(role) and mapping[role] not in header:
            raise InvalidInput(f"Missing optional mapped column: {role}")
    result = {}
    for source in rows:
        key = source[mapping["key"]]
        if not key.strip() or key in result:
            raise InvalidInput("Blank or duplicate stable key")
        row = {"x": number(source[mapping["x"]], "x"), "y": number(source[mapping["y"]], "y"), "source": source}
        if old:
            lx, ly = source[mapping["labelX"]], source[mapping["labelY"]]
            if bool(lx.strip()) != bool(ly.strip()):
                raise InvalidInput("Half-empty label coordinates")
            row["label"] = None if not lx.strip() else (number(lx, "labelX"), number(ly, "labelY"))
            rotation = source[mapping["rotation"]] if mapping.get("rotation") else "0"
            row["rotation"] = number(rotation or "0", "rotation")
            show = source[mapping["show"]] if mapping.get("show") else "1"
            normalized_show = show.strip().lower()
            if normalized_show not in ("", "0", "1", "true", "false"):
                raise InvalidInput("Show must be blank, 0, 1, true, or false")
            row["show"] = "0" if normalized_show in ("0", "false") else "1"
        else:
            row["text"] = source[mapping["text"]]
            if not row["text"].strip() or "\n" in row["text"] or "\r" in row["text"]:
                raise InvalidInput("V1 labels must be nonblank and single-line")
        result[key] = row
    return result


def mapping_for(request: dict, side: str) -> dict:
    """Public mappings are partial overrides of the documented defaults."""
    defaults = OLD_MAPPING if side == "old" else NEW_MAPPING
    return {**defaults, **request.get(side + "Mapping", {})}


def expected_rows(request: dict) -> list[dict]:
    if request.get("oldCRS") != request.get("newCRS") or not valid_crs(request.get("oldCRS", "")):
        raise InvalidInput("Mismatched, geographic, or unsupported CRS")
    old = keyed(request["oldCSV"], mapping_for(request, "old"), True)
    new = keyed(request["newCSV"], mapping_for(request, "new"), False)
    decisions = request.get("decisions", {})
    result = []
    for key, newrow in new.items():
        source = old.get(key)
        label = source["label"] if source else None
        rotation = source["rotation"] if source else Decimal(0)
        show = source["show"] if source else "1"
        moved = source and (source["x"], source["y"]) != (newrow["x"], newrow["y"])
        if moved and label:
            decision = decisions.get(key)
            if decision not in ("keep", "follow", "reset"):
                raise InvalidInput(f"Decision required: {key}")
            if decision == "follow":
                # Difference first: independent point-to-label offset specification.
                # Never inherit Python's default 28-digit arithmetic precision.
                with localcontext(ORACLE_CONTEXT):
                    offset_x, offset_y = label[0] - source["x"], label[1] - source["y"]
                    label = newrow["x"] + offset_x, newrow["y"] + offset_y
            elif decision == "reset":
                label, rotation = None, Decimal(0)
        result.append(dict(zip(COLUMNS, [key, newrow["x"], newrow["y"], newrow["text"], label[0] if label else "", label[1] if label else "", rotation, show, "pinned" if label else "auto"])))
    return result


def assert_rows(actual: list[dict], expected: list[dict]) -> None:
    assert len(actual) == len(expected), f"Row count {len(actual)} != {len(expected)}"
    by_key = {}
    for row in actual:
        assert isinstance(row.get("stable_key"), str), "Stable keys must be strings"
        assert row["stable_key"] not in by_key, "Output contains duplicate stable keys"
        by_key[row["stable_key"]] = row
    assert set(by_key) == {row["stable_key"] for row in expected}, "Output stable-key set differs"
    for wanted in expected:
        row = by_key[wanted["stable_key"]]
        for field in COLUMNS:
            assert field in row, f"Output missing {field}"
            got, want = row[field], wanted[field]
            if field in NUMERIC_COLUMNS and want != "":
                # Decimal equality is exact and does not round via subtraction.
                assert number(got, field) == number(want, field), f"{wanted['stable_key']}/{field}: {got!r} != {want!r}"
            elif field in ("label_x", "label_y"):
                assert got in ("", None), f"{wanted['stable_key']}/{field}: auto must have no coordinate"
            else:
                assert str(got) == str(want), f"{wanted['stable_key']}/{field}: {got!r} != {want!r}"


def source_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
