#!/usr/bin/env python3
"""Convert rAthena ITEM_DB YAML into CSV, JSON, and a searchable offline viewer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Install the pinned helper dependency with "
        "python -m pip install -r tools/requirements-rathena-items.txt"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "references" / "rathena" / "db" / "re"
DEFAULT_OUTPUT = ROOT / "exports" / "rathena-items"
CSV_FIELDS = [
    "Id", "AegisName", "Name", "Type", "SubType", "Buy", "Sell", "Weight",
    "Attack", "MagicAttack", "Defense", "Range", "Slots", "WeaponLevel",
    "ArmorLevel", "EquipLevelMin", "EquipLevelMax", "Refineable", "Gradable",
    "View", "Jobs", "Classes", "Locations", "SourceFile", "AdditionalDataJSON",
]
SIMPLE_FIELDS = set(CSV_FIELDS) - {"Jobs", "Classes", "Locations", "SourceFile", "AdditionalDataJSON"}


def source_revision(source: Path) -> str:
    """Return the local source repository revision when source is in a Git checkout."""
    repo = source.parent.parent if source.is_dir() else source.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def load_items(source: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not source.exists():
        raise ValueError(f"Source path does not exist: {source}")
    files = [source] if source.is_file() else sorted(source.glob("item_db*.yml"))
    if not files:
        raise ValueError(f"No item_db*.yml files found under: {source}")

    items: list[dict[str, Any]] = []
    source_receipts: list[dict[str, str]] = []
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        try:
            document = yaml.safe_load(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise ValueError(f"Cannot parse {path}{where}: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"Expected a YAML mapping in {path}")
        header = document.get("Header")
        if not isinstance(header, dict) or header.get("Type") != "ITEM_DB":
            raise ValueError(f"Expected Header.Type: ITEM_DB in {path}")
        body = document.get("Body", [])
        if body is None:
            body = []
        if not isinstance(body, list):
            raise ValueError(f"Expected Body to be a list in {path}")
        try:
            relpath = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relpath = path.name
        source_receipts.append({"path": relpath, "sha256": digest, "items": str(len(body))})
        for row_number, record in enumerate(body, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"{path}: Body entry {row_number} is not a mapping")
            item = dict(record)
            item["SourceFile"] = relpath
            items.append(item)
    items.sort(key=item_sort_key)
    return items, source_receipts


def item_sort_key(item: dict[str, Any]) -> tuple[int, Any, str]:
    item_id = item.get("Id")
    if isinstance(item_id, int) and not isinstance(item_id, bool):
        return (0, item_id, str(item.get("AegisName", "")))
    if isinstance(item_id, str) and item_id.isdigit():
        return (0, int(item_id), str(item.get("AegisName", "")))
    return (1, str(item_id), str(item.get("AegisName", "")))


def json_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def safe_csv_text(value: str) -> str:
    """Prevent spreadsheet formula execution in text fields when opened as CSV."""
    if value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def write_csv(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row: dict[str, Any] = {}
            known = {key for key in item if key != "SourceFile"}
            for field in CSV_FIELDS:
                if field == "AdditionalDataJSON":
                    value = {key: item[key] for key in sorted(known - SIMPLE_FIELDS)}
                    row[field] = json_cell(value)
                elif field in ("Jobs", "Classes", "Locations"):
                    row[field] = json_cell(item.get(field))
                elif field in item:
                    value = item[field]
                    row[field] = safe_csv_text(str(value)) if isinstance(value, str) else json_cell(value)
                else:
                    row[field] = ""
            row["SourceFile"] = item.get("SourceFile", "")
            writer.writerow(row)


def safe_script_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def make_html(items: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    embedded = safe_script_json(items)
    meta_text = html.escape(
        f"{meta['count']:,} items • source revision {meta['source_revision']} • "
        f"{meta['generated_at']}"
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>rAthena Item Browser</title>
<style>
:root{color-scheme:dark;font:15px/1.45 system-ui,sans-serif;background:#10151c;color:#e7edf6}body{margin:0;padding:24px;max-width:1500px;margin-inline:auto}h1{margin:.2em 0}small,.muted{color:#9aa9bc}.bar{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}input,select{background:#1d2733;color:inherit;border:1px solid #465669;border-radius:8px;padding:11px;min-width:200px}input{flex:1}button{background:#24364b;color:inherit;border:1px solid #58708b;border-radius:6px;padding:7px 10px;cursor:pointer}button:hover{background:#304960}.wrap{overflow:auto;border:1px solid #334354;border-radius:10px}table{border-collapse:collapse;width:100%;min-width:1000px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #293542}th{position:sticky;top:0;background:#18222e}tr:hover{background:#1a2633}.num{text-align:right;font-variant-numeric:tabular-nums}.pill{color:#a9d5ff}.status{margin:8px 0 14px}dialog{max-width:min(900px,92vw);max-height:86vh;background:#131c26;color:inherit;border:1px solid #53677f;border-radius:12px}dialog::backdrop{background:#000b}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:65vh;overflow:auto;font-size:12px}footer{margin-top:18px;color:#9aa9bc;font-size:12px}
</style></head><body>
<h1>rAthena Item Browser</h1><div class="muted">Local read-only view of item database fields. Script fields are displayed as data and never executed.</div>
<div class="bar"><input id="q" type="search" placeholder="Search name, Aegis name, ID or item data…" autocomplete="off"><select id="type"><option value="">All item types</option></select></div>
<div id="status" class="status muted"></div><div class="wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Aegis name</th><th>Type</th><th>Subtype</th><th>Buy</th><th>Weight</th><th>Attack</th><th>Defense</th><th>Slots</th><th>Source</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
<footer>""" + meta_text + """ · Data is from a GPL-3.0 rAthena checkout. See the adjacent license notice.</footer>
<dialog id="detail"><form method="dialog"><button style="float:right">Close</button></form><h2 id="detailTitle"></h2><pre id="detailBody"></pre></dialog>
<script>
const ITEMS = """ + embedded + """;
const q=document.getElementById('q'), type=document.getElementById('type'), rows=document.getElementById('rows'), status=document.getElementById('status');
const detail=document.getElementById('detail'), detailTitle=document.getElementById('detailTitle'), detailBody=document.getElementById('detailBody');
const text=v=>v==null?'':typeof v==='object'?JSON.stringify(v):String(v);
const types=[...new Set(ITEMS.map(x=>text(x.Type)).filter(Boolean))].sort();
for(const t of types){const o=document.createElement('option');o.value=t;o.textContent=t;type.append(o)}
function render(){const needle=q.value.trim().toLocaleLowerCase();const chosen=type.value;const matches=[];
 for(let i=0;i<ITEMS.length;i++){const x=ITEMS[i];if(chosen&&text(x.Type)!==chosen)continue;const hay=[x.Id,x.Name,x.AegisName,x.Type,x.SubType,x.SourceFile].map(text).join(' ').toLocaleLowerCase();if(needle&&!hay.includes(needle))continue;matches.push(i)}
 rows.replaceChildren();for(const i of matches.slice(0,200)){const x=ITEMS[i],tr=document.createElement('tr');
 const fields=[x.Id,x.Name,x.AegisName,x.Type,x.SubType,x.Buy,x.Weight,x.Attack,x.Defense,x.Slots,x.SourceFile];
 for(let j=0;j<fields.length;j++){const td=document.createElement('td');td.textContent=text(fields[j]);if(j===0||[5,6,7,8,9].includes(j))td.className='num';if(j===3)td.className='pill';tr.append(td)}
 const td=document.createElement('td'),b=document.createElement('button');b.textContent='Details';b.dataset.index=String(i);td.append(b);tr.append(td);rows.append(tr)}
 status.textContent=`${matches.length.toLocaleString()} matches; showing ${Math.min(matches.length,200).toLocaleString()}`;
}
document.addEventListener('input',e=>{if(e.target===q)render()});type.addEventListener('change',render);
document.addEventListener('click',e=>{const b=e.target.closest('button[data-index]');if(!b)return;const item=ITEMS[Number(b.dataset.index)];detailTitle.textContent=`${text(item.Name)} (#${text(item.Id)})`;detailBody.textContent=JSON.stringify(item,null,2);detail.showModal()});
render();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="A db/re directory or one ITEM_DB YAML file")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT, help="Output directory for CSV, JSON, HTML and license notice")
    parser.add_argument("--format", choices=("all", "csv", "json", "html"), default="all")
    parser.add_argument("--force", action="store_true", help="Replace generated outputs in the selected output directory")
    args = parser.parse_args()

    source = args.source.resolve()
    out_dir = args.out_dir.resolve()
    items, sources = load_items(source)
    outputs = {
        "csv": out_dir / "items.csv",
        "json": out_dir / "items.json",
        "html": out_dir / "index.html",
        "notice": out_dir / "LICENSE-NOTICE.txt",
    }
    selected = ("csv", "json", "html") if args.format == "all" else (args.format,)
    selected_paths = [outputs[name] for name in selected] + [outputs["notice"]]
    existing = [path for path in selected_paths if path.exists()]
    if existing and not args.force:
        raise SystemExit("Output exists; refusing to overwrite. Use --force to regenerate: " + ", ".join(map(str, existing)))

    out_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    meta = {
        "format_version": 1,
        "source_revision": source_revision(source),
        "source_path": str(source),
        "source_files": sources,
        "count": len(items),
        "generated_at": generated,
        "source_license": "GNU GPL v3.0; see references/rathena/LICENSE",
        "note": "Item script fields are data only and are never executed by this converter or HTML viewer.",
    }
    if "csv" in selected:
        write_csv(outputs["csv"], items)
    if "json" in selected:
        outputs["json"].write_text(json.dumps({"metadata": meta, "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if "html" in selected:
        outputs["html"].write_text(make_html(items, meta), encoding="utf-8")
    license_path = ROOT / "references" / "rathena" / "LICENSE"
    notice = (
        "These exports contain data derived from the local rAthena source checkout.\n"
        "Source revision: " + meta["source_revision"] + "\n"
        "The rAthena repository states GNU GPL version 3.0; consult the complete license at:\n"
        + str(license_path) + "\n"
        "The viewer displays Script/EquipScript fields as text. It does not interpret or execute them.\n"
    )
    outputs["notice"].write_text(notice, encoding="utf-8")
    print(json.dumps({"status": "ok", "count": len(items), "source_revision": meta["source_revision"],
                      "output_dir": str(out_dir), "generated": [str(outputs[name]) for name in selected] + [str(outputs["notice"])],
                      "source_files": sources}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"rathena_items: {exc}", file=sys.stderr)
        raise SystemExit(2)
