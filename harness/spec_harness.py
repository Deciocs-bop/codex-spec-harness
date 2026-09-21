"""Validate concise, evidence-based specification artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_PACKET_FIELDS = {"id", "objective", "sources", "decisions", "scope", "acceptance", "open_decisions", "limits"}
COMPLETION_STATES = {"implemented", "released"}


@dataclass(frozen=True)
class Issue:
    code: str
    detail: str


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ValueError(f"path escapes project root: {relative}")
    return candidate


def words(value: str) -> int:
    return len(value.split())


def validate(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    required = ["project-profile.yaml", "status.md", "decisions.md", "traceability.yaml", "sources.yaml", "tasks"]
    for name in required:
        if not (root / name).exists():
            issues.append(Issue("missing_artifact", name))
    if issues:
        return issues

    profile = read_yaml(root / "project-profile.yaml") or {}
    budget = profile.get("context", {}).get("max_words")
    if not isinstance(budget, int) or budget < 100:
        issues.append(Issue("invalid_budget", "project-profile.yaml context.max_words must be an integer >= 100"))

    decisions = (root / "decisions.md").read_text(encoding="utf-8")
    decision_ids = [line.split(" ", 1)[0] for line in decisions.splitlines() if line.startswith("ADR-")]
    if len(decision_ids) != len(set(decision_ids)):
        issues.append(Issue("duplicate_decision", "decision IDs must be unique"))

    manifest = read_yaml(root / "sources.yaml") or {}
    for source in manifest.get("sources", []):
        path = resolve(root, source.get("path", ""))
        if not path.is_file():
            issues.append(Issue("missing_source", source.get("path", "")))
        elif source.get("sha256") != digest(path):
            issues.append(Issue("source_changed", source.get("path", "")))

    trace = read_yaml(root / "traceability.yaml") or {}
    for row in trace.get("requirements", []):
        for field in ("id", "source", "decision", "contract", "tests", "evidence"):
            if not row.get(field):
                issues.append(Issue("trace_missing", f"{row.get('id', '?')}:{field}"))
        evidence = row.get("evidence", {})
        if row.get("state") in COMPLETION_STATES and evidence.get("kind") != "executed":
            issues.append(Issue("unproven_completion", row.get("id", "?")))

    for packet_path in sorted((root / "tasks").glob("*.yaml")):
        packet = read_yaml(packet_path) or {}
        missing = REQUIRED_PACKET_FIELDS - set(packet)
        if missing:
            issues.append(Issue("packet_missing", f"{packet_path.name}:{','.join(sorted(missing))}"))
        if isinstance(budget, int) and words(json.dumps(packet, ensure_ascii=False)) > budget:
            issues.append(Issue("packet_over_budget", packet_path.name))
    return issues


def print_context(root: Path, task_id: str) -> int:
    packets = [read_yaml(path) or {} for path in (root / "tasks").glob("*.yaml")]
    packet = next((item for item in packets if item.get("id") == task_id), None)
    if not packet:
        print(f"ERROR: unknown task {task_id}")
        return 1
    profile = read_yaml(root / "project-profile.yaml") or {}
    budget = profile["context"]["max_words"]
    text = "\n".join([
        f"# {packet['id']}: {packet['objective']}",
        f"Sources: {', '.join(packet['sources'])}",
        f"Decisions: {', '.join(packet['decisions'])}",
        f"Scope: {packet['scope']}",
        f"Acceptance: {packet['acceptance']}",
        f"Open decisions: {packet['open_decisions']}",
        f"Limits: {packet['limits']}",
    ])
    if words(text) > budget:
        print("ERROR: rendered context exceeds configured budget")
        return 1
    print(text)
    return 0


def refresh_hashes(root: Path) -> None:
    manifest_path = root / "sources.yaml"
    manifest = read_yaml(manifest_path) or {"sources": []}
    for source in manifest["sources"]:
        source["sha256"] = digest(resolve(root, source["path"]))
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "context", "hash"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--task")
    args = parser.parse_args()
    if args.command == "validate":
        issues = validate(args.root)
        for issue in issues:
            print(f"ERROR: {issue.code}: {issue.detail}")
        print("OK" if not issues else f"BLOCK: {len(issues)} issue(s)")
        return int(bool(issues))
    if args.command == "context":
        return print_context(args.root, args.task or "")
    refresh_hashes(args.root)
    print("OK: source hashes refreshed; assess impact before accepting source changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
