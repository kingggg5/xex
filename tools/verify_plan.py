"""Verify planning links, assumptions and independently derived capacity examples."""

import copy
import json
import re
import subprocess
from pathlib import Path

from capacity_model import calculate

# Areas that are deliberately gitignored provenance data: a missing link there
# means the folder was not checked out, not that a document drifted.
PROVENANCE_AREAS = ("references/rathena", "exports")


def prose_lines(body):
    """Fenced blocks are examples, not live content: (original line number, line) outside them."""
    result = []
    in_fence = False
    for number, line in enumerate(body.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((number, line))
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    documents = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    errors = []
    warnings = []
    checked_links = 0
    bodies = {}
    for path in documents:
        body = path.read_text(encoding="utf-8")
        bodies[path] = body
        if body.count("```") % 2:
            errors.append(f"Unclosed code fence: {path.name}")
        if "\ufffd" in body:
            errors.append(f"Encoding replacement character: {path.name}")
        prose = "\n".join(line for _, line in prose_lines(body))
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", prose):
            if target.startswith(("https://", "http://", "#")):
                continue
            checked_links += 1
            local = (path.parent / target.split("#", 1)[0]).resolve()
            if not local.is_relative_to(root):
                errors.append(f"Escaping link in {path.name}: {target}")
                continue
            if local.exists():
                continue
            relative = local.relative_to(root).as_posix()
            if any(relative == area or relative.startswith(area + "/") for area in PROVENANCE_AREAS):
                warnings.append(f"Provenance area not checked out, link unchecked: {path.name}: {target}")
            else:
                errors.append(f"Broken link in {path.name}: {target}")

    config = json.loads((root / "planning/capacity-assumptions.json").read_text(encoding="utf-8"))
    report = calculate(config)
    ten_k = next(row for row in report["scenarios"] if row["peak_ccu"] == 10000)
    # Independent unit derivation: 3500 users * 7.5 KB/s * 2,592,000 seconds.
    expected_gb = 3500 * 7500 * 2592000 / 1_000_000_000
    if ten_k["monthly_realtime_outbound_gb"] != expected_gb or expected_gb != 68040:
        errors.append("10k scenario monthly bandwidth example does not equal 68,040 GB")
    if ten_k["peak_outbound_mbps"] != 600 or ten_k["world_nodes_including_reserve"] != 16:
        errors.append("10k peak bandwidth or fleet reserve arithmetic is inconsistent")
    if report["prices_complete"] or any(row["partial_monthly_cost_thb"] is not None for row in report["scenarios"]):
        errors.append("Missing prices were presented as a cost estimate")
    priced = copy.deepcopy(config)
    priced["prices_thb"].update(world_node_per_month=100, fixed_services_per_month=200,
                               realtime_egress_per_gb=2, included_realtime_egress_gb=70000)
    priced_row = calculate(priced)["scenarios"][-1]
    if priced_row["partial_monthly_cost_thb"] != 1800:
        errors.append("Included bandwidth must not create a negative egress charge")
    for key, value in (("admission_fraction", 0), ("average_to_peak_ratio", 2),
                       ("failure_reserve_nodes", -1), ("outbound_kbit_per_active_player", float("nan"))):
        invalid = copy.deepcopy(config)
        invalid[key] = value
        try:
            calculate(invalid)
        except ValueError:
            continue
        errors.append(f"Invalid capacity input accepted: {key}")

    for invalid_allowance in (-1, "100", float("inf"), None):
        invalid = copy.deepcopy(config)
        invalid["prices_thb"]["included_realtime_egress_gb"] = invalid_allowance
        try:
            calculate(invalid)
        except ValueError:
            continue
        errors.append("Invalid included egress allowance accepted")

    # Scan authored files only, without reproducing any matching secret value.
    authored = documents + list((root / "planning").rglob("*.json")) + list((root / "tools").glob("*.py"))
    secret_pattern = re.compile(r"(?:apikey_[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{20,})")
    for path in authored:
        if secret_pattern.search(path.read_text(encoding="utf-8")):
            errors.append(f"Potential credential in artifact: {path.relative_to(root)}")

    # The README must name the protocol version the server actually speaks.
    wire_source = (root / "apps/server/src/wire.rs").read_text(encoding="utf-8")
    wire_version = re.search(r"pub const PROTOCOL_VERSION: u8 = (\d+);", wire_source)
    readme_version = re.search(r"binary v(\d+)", bodies[root / "README.md"])
    if not wire_version or not readme_version:
        errors.append("Protocol version not found in wire.rs or README.md")
    elif wire_version.group(1) != readme_version.group(1):
        errors.append(
            f"README says binary v{readme_version.group(1)} but wire.rs PROTOCOL_VERSION is {wire_version.group(1)}"
        )

    # Closed backlog rows must link evidence that exists, matches the item, and names a commit in history.
    # Evidence recorded before the 2026-09-25 camelCase schema rule may lack a commit; that stays a warning
    # because evidence files are immutable (plan §20).
    for row in (root / "docs/execution-backlog.md").read_text(encoding="utf-8").splitlines():
        if not row.startswith("|"):
            continue
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[2].startswith("Closed"):
            continue
        item_id = cells[0].split()[0] if cells[0] else "unknown row"
        link = re.search(r"\]\((\.\./planning/evidence/[^)]+\.json)\)", row)
        if not link:
            errors.append(f"Closed row has no evidence link: {item_id}")
            continue
        evidence_path = (root / "docs" / link.group(1)).resolve()
        if not evidence_path.exists():
            errors.append(f"Closed row evidence file is missing: {item_id}")
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            errors.append(f"Closed row evidence is not readable JSON: {item_id}")
            continue
        work_item = evidence.get("work_item")
        if isinstance(work_item, str) and work_item != item_id:
            errors.append(f"Evidence work_item {work_item!r} does not match row {item_id}")
        commit = evidence.get("sourceCommit") or evidence.get("source_commit")
        if commit and re.fullmatch(r"[0-9a-f]{7,40}", str(commit)):
            found = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                capture_output=True,
            )
            if found.returncode != 0:
                errors.append(f"Evidence commit {commit} for {item_id} is not in git history")
        elif commit:
            warnings.append(f"Evidence for {item_id} names a non-hash source commit: {commit}")
        else:
            warnings.append(f"Evidence for {item_id} records no source commit (pre-2026-09-25 schema)")

    # Live-status wording belongs in the backlog's live table only; fenced examples are prose.
    status_cell = re.compile(r"\|\s*(Closed|Next|Not started|In progress|Reopened|Blocked)\s*\|")
    for path, body in bodies.items():
        if path.name == "execution-backlog.md":
            continue
        for number, line in prose_lines(body):
            if status_cell.search(line):
                errors.append(f"Live-status prose outside the backlog table: {path.name}:{number}")

    output = {"status": "PASS" if not errors else "FAIL", "documents_checked": len(documents),
              "local_links_checked": checked_links,
              "checks": ["Markdown code fences", "UTF-8 text", "local links (gitignored provenance areas warn)",
                         "capacity unit arithmetic", "unknown-price handling", "included-egress floor",
                         "invalid-input rejection", "credential-pattern scan of authored artifacts",
                         "README protocol version equals wire.rs PROTOCOL_VERSION",
                         "closed backlog rows link existing evidence naming real commits",
                         "live-status wording confined to the backlog table"],
              "warnings": warnings,
              "limitations": ["No production-ready gameplay or scale benchmark tested", "No legal clearance",
                              "Static checks do not prove planning quality; separate review required"],
              "errors": errors}
    target = root / "planning/evidence/plan-verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
