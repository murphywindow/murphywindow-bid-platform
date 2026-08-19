"""Import the owner-provided two-column codes.xlsx into versioned JSON reference data.

The workbook is read as Open XML without changing it. Duplicate normalized codes
are retained as source variants/description aliases under one stable record.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def normalize(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


def extract(path: Path) -> list[dict]:
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//m:sheetData/m:row", NS):
            cells: dict[str, str] = {}
            for cell in row.findall("m:c", NS):
                column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                value_node = cell.find("m:v", NS)
                inline = cell.find("m:is", NS)
                if cell.attrib.get("t") == "s" and value_node is not None:
                    value = shared[int(value_node.text)]
                elif cell.attrib.get("t") == "inlineStr" and inline is not None:
                    value = "".join(t.text or "" for t in inline.findall(".//m:t", NS))
                else:
                    value = value_node.text if value_node is not None else ""
                cells[column] = (value or "").strip()
            code, description = cells.get("A", ""), cells.get("B", "")
            if not code or not description:
                raise ValueError(f"Source row {row.attrib.get('r')} requires both code and description")
            rows.append({"row": int(row.attrib["r"]), "code": code, "description": description})
        return rows


def build(path: Path) -> dict:
    rows = extract(path)
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        grouped.setdefault(normalize(row["code"]), []).append(row)
    records = []
    duplicates = []
    for key, variants in grouped.items():
        first = variants[0]
        descriptions = list(dict.fromkeys(item["description"] for item in variants))
        record = {
            "id": f"csi_{key.lower()}", "normalized_code": key, "display_code": first["code"], "description": first["description"],
            "description_aliases": descriptions[1:], "category": "General" if key.startswith("GEN") else "CSI MasterFormat",
            "division": first["code"][:2] if first["code"][:2].isdigit() else "GEN", "subdivision": "", "vendor_category": "",
            "vendors": [], "agents": [], "contacts": [], "emails": [], "phone_numbers": [], "friendly_names": [], "notes": "",
            "active": True, "status": "owner_confirmed_reference", "source_rows": [item["row"] for item in variants]
        }
        records.append(record)
        if len(variants) > 1:
            duplicates.append({"normalized_code": key, "display_code": first["code"], "variants": variants})
    stat = path.stat()
    return {
        "schema_version": "1.0.0", "reference_id": "owner-cost-codes-2026-08-17-v1",
        "source": {"file_name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(), "worksheet": "Sheet1", "columns": ["code", "description"]},
        "source_row_count": len(rows), "unique_code_count": len(records), "duplicate_normalized_codes": duplicates, "records": records
    }


def main() -> None:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\MicahJohnson\Downloads\codes.xlsx")
    output = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "data" / "reference" / "codes.json")
    payload = build(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, output)
    print(json.dumps({"output": str(output), "source_rows": payload["source_row_count"], "unique_codes": payload["unique_code_count"], "duplicates": len(payload["duplicate_normalized_codes"]), "sha256": payload["source"]["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
