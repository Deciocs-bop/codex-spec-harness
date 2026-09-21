"""Validate concise, evidence-based specification artifacts."""
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_ARTIFACTS = (
    "project-profile.yaml",
    "status.md",
    "decisions.md",
    "contracts.yaml",
    "tests.yaml",
    "evidence.yaml",
    "traceability.yaml",
    "sources.yaml",
    "tasks",
)
REQUIRED_PACKET_FIELDS = {
    "id",
    "objective",
    "sources",
    "decisions",
    "requirements",
    "scope",
    "acceptance",
    "open_decisions",
    "blockers",
    "autonomy",
    "limits",
}
REQUIRED_REQUIREMENT_FIELDS = {"id", "source", "decision", "contract", "test", "evidence", "state"}
DECISION_STATES = {"proposed", "approved", "superseded", "rejected"}
CONTRACT_STATES = {"approved", "future"}
TEST_STATES = {"planned", "executed"}
EVIDENCE_KINDS = {"documentary", "executed"}
REQUIREMENT_STATES = {"specified", "implementation_ready", "implemented", "released"}
COMPLETION_STATES = {"implemented", "released"}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".py", ".txt"}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)\s]+)")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
)


@dataclass(frozen=True)
class Issue:
    code: str
    detail: str


@dataclass
class Model:
    root: Path
    profile: dict[str, Any]
    decisions: dict[str, str]
    sources: dict[str, str]
    contracts: dict[str, dict[str, Any]]
    tests: dict[str, dict[str, Any]]
    evidence: dict[str, dict[str, Any]]
    requirements: dict[str, dict[str, Any]]
    packets: list[tuple[Path, dict[str, Any]]]
    issues: list[Issue]


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


def add_yaml_issue(issues: list[Issue], path: Path, error: Exception) -> None:
    issues.append(Issue("invalid_yaml", f"{path.name}: {error}"))


def read_mapping(path: Path, issues: list[Issue]) -> dict[str, Any]:
    try:
        value = read_yaml(path)
    except (OSError, yaml.YAMLError) as error:
        add_yaml_issue(issues, path, error)
        return {}
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append(Issue("invalid_yaml", f"{path.name}: expected mapping"))
        return {}
    return value


def read_records(path: Path, key: str, issues: list[Issue]) -> list[dict[str, Any]]:
    value = read_mapping(path, issues).get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        issues.append(Issue("invalid_yaml", f"{path.name}: {key} must be a list of mappings"))
        return []
    return value


def index_records(
    records: list[dict[str, Any]],
    label: str,
    issues: list[Issue],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            issues.append(Issue("missing_id", label))
            continue
        if identifier in indexed:
            issues.append(Issue("duplicate_id", f"{label}:{identifier}"))
            continue
        indexed[identifier] = record
    return indexed


def parse_decisions(path: Path, issues: list[Issue]) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.startswith("ADR-"):
            continue
        parts = [part.strip() for part in line.split("|", maxsplit=3)]
        if len(parts) != 4:
            issues.append(Issue("invalid_decision", f"{path.name}:{line_number}"))
            continue
        identifier, state = parts[0], parts[1]
        if state not in DECISION_STATES:
            issues.append(Issue("invalid_decision_state", f"{identifier}:{state}"))
        if identifier in decisions:
            issues.append(Issue("duplicate_id", f"decision:{identifier}"))
            continue
        decisions[identifier] = state
    return decisions


def source_path(reference: str) -> str:
    return reference.split("#", maxsplit=1)[0]


def source_integrity(root: Path, sources: dict[str, str], reference: str) -> Issue | None:
    path_text = source_path(reference)
    expected_hash = sources.get(path_text)
    if expected_hash is None:
        return Issue("orphan_source", path_text)
    try:
        path = resolve(root, path_text)
    except ValueError:
        return Issue("invalid_path", path_text)
    if not path.is_file():
        return Issue("missing_source", path_text)
    if expected_hash != digest(path):
        return Issue("source_changed", path_text)
    return None


def load_model(root: Path) -> Model:
    issues: list[Issue] = []
    for name in REQUIRED_ARTIFACTS:
        if not (root / name).exists():
            issues.append(Issue("missing_artifact", name))
    if issues:
        return Model(root, {}, {}, {}, {}, {}, {}, {}, [], issues)

    profile = read_mapping(root / "project-profile.yaml", issues)
    decisions = parse_decisions(root / "decisions.md", issues)
    source_records = read_records(root / "sources.yaml", "sources", issues)
    sources: dict[str, str] = {}
    for source in source_records:
        path = source.get("path")
        hash_value = source.get("sha256")
        if not isinstance(path, str) or not isinstance(hash_value, str):
            issues.append(Issue("invalid_source", "sources.yaml"))
            continue
        if path in sources:
            issues.append(Issue("duplicate_id", f"source:{path}"))
            continue
        sources[path] = hash_value

    contracts = index_records(read_records(root / "contracts.yaml", "contracts", issues), "contract", issues)
    tests = index_records(read_records(root / "tests.yaml", "tests", issues), "test", issues)
    evidence = index_records(read_records(root / "evidence.yaml", "evidence", issues), "evidence", issues)
    requirements = index_records(
        read_records(root / "traceability.yaml", "requirements", issues), "requirement", issues
    )

    packets: list[tuple[Path, dict[str, Any]]] = []
    for packet_path in sorted((root / "tasks").glob("*.yaml")):
        packet = read_mapping(packet_path, issues)
        packets.append((packet_path, packet))
    return Model(root, profile, decisions, sources, contracts, tests, evidence, requirements, packets, issues)


def validate_profile(model: Model) -> list[Issue]:
    budget = model.profile.get("context", {}).get("max_words")
    if not isinstance(budget, int) or budget < 100:
        return [Issue("invalid_budget", "project-profile.yaml context.max_words must be an integer >= 100")]
    return []


def validate_sources(model: Model) -> list[Issue]:
    issues: list[Issue] = []
    for path_text in model.sources:
        issue = source_integrity(model.root, model.sources, path_text)
        if issue:
            issues.append(issue)
    return issues


def validate_catalog_states(model: Model) -> list[Issue]:
    issues: list[Issue] = []
    for identifier, contract in model.contracts.items():
        if contract.get("status") not in CONTRACT_STATES:
            issues.append(Issue("invalid_contract_state", identifier))
    for identifier, test in model.tests.items():
        if test.get("status") not in TEST_STATES:
            issues.append(Issue("invalid_test_state", identifier))
    for identifier, evidence in model.evidence.items():
        if evidence.get("kind") not in EVIDENCE_KINDS:
            issues.append(Issue("invalid_evidence_kind", identifier))
        path = evidence.get("path")
        if not isinstance(path, str):
            issues.append(Issue("missing_evidence_path", identifier))
        else:
            try:
                if not resolve(model.root, path).is_file():
                    issues.append(Issue("missing_evidence", f"{identifier}:{path}"))
            except ValueError:
                issues.append(Issue("invalid_path", path))
        source_hashes = evidence.get("source_hashes")
        if not isinstance(source_hashes, dict):
            issues.append(Issue("missing_evidence_hashes", identifier))
            continue
        for reference, expected_hash in source_hashes.items():
            if not isinstance(reference, str) or not isinstance(expected_hash, str):
                issues.append(Issue("invalid_evidence_hash", identifier))
                continue
            source_issue = source_integrity(model.root, model.sources, reference)
            if source_issue:
                issues.append(Issue("evidence_source_changed", f"{identifier}:{reference}"))
                continue
            if expected_hash != model.sources.get(source_path(reference)):
                issues.append(Issue("evidence_source_changed", f"{identifier}:{reference}"))
    return issues


def validate_requirements(model: Model) -> list[Issue]:
    issues: list[Issue] = []
    for identifier, requirement in model.requirements.items():
        missing = REQUIRED_REQUIREMENT_FIELDS - set(requirement)
        for field in sorted(missing):
            issues.append(Issue("trace_missing", f"{identifier}:{field}"))
        if requirement.get("state") not in REQUIREMENT_STATES:
            issues.append(Issue("invalid_requirement_state", identifier))
        source = requirement.get("source")
        if isinstance(source, str):
            source_issue = source_integrity(model.root, model.sources, source)
            if source_issue:
                issues.append(source_issue)
        else:
            issues.append(Issue("orphan_source", identifier))
        decision = requirement.get("decision")
        if decision not in model.decisions:
            issues.append(Issue("orphan_decision", f"{identifier}:{decision}"))
        elif model.decisions[decision] != "approved":
            issues.append(Issue("unapproved_decision", f"{identifier}:{decision}"))
        contract = model.contracts.get(requirement.get("contract"))
        if contract is None:
            issues.append(Issue("orphan_contract", f"{identifier}:{requirement.get('contract')}"))
        test = model.tests.get(requirement.get("test"))
        if test is None:
            issues.append(Issue("orphan_test", f"{identifier}:{requirement.get('test')}"))
        evidence = model.evidence.get(requirement.get("evidence"))
        if evidence is None:
            issues.append(Issue("orphan_evidence", f"{identifier}:{requirement.get('evidence')}"))
        for dependency in requirement.get("depends_on", []):
            if dependency not in model.requirements or dependency == identifier:
                issues.append(Issue("orphan_requirement", f"{identifier}:{dependency}"))
        if requirement.get("state") in COMPLETION_STATES:
            if not contract or contract.get("status") != "approved":
                issues.append(Issue("unproven_completion", f"{identifier}:approved_contract"))
            if not test or test.get("status") != "executed":
                issues.append(Issue("unproven_completion", f"{identifier}:executed_test"))
            if not evidence or evidence.get("kind") != "executed":
                issues.append(Issue("unproven_completion", f"{identifier}:executed_evidence"))
    return issues


def validate_packet(model: Model, path: Path, packet: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    missing = REQUIRED_PACKET_FIELDS - set(packet)
    if missing:
        issues.append(Issue("packet_missing", f"{path.name}:{','.join(sorted(missing))}"))
    identifier = packet.get("id", path.stem)
    for source in packet.get("sources", []):
        if not isinstance(source, str):
            issues.append(Issue("packet_orphan_source", f"{identifier}:{source}"))
            continue
        source_issue = source_integrity(model.root, model.sources, source)
        if source_issue:
            issues.append(Issue("packet_source_invalid", f"{identifier}:{source_issue.detail}"))
    for decision in packet.get("decisions", []):
        if decision not in model.decisions:
            issues.append(Issue("packet_orphan_decision", f"{identifier}:{decision}"))
    for requirement in packet.get("requirements", []):
        if requirement not in model.requirements:
            issues.append(Issue("packet_orphan_requirement", f"{identifier}:{requirement}"))
    budget = model.profile.get("context", {}).get("max_words")
    if isinstance(budget, int) and words(str(packet)) > budget:
        issues.append(Issue("packet_over_budget", path.name))
    return issues


def validate(root: Path) -> list[Issue]:
    model = load_model(root)
    issues = list(model.issues)
    if issues:
        return issues
    issues.extend(validate_profile(model))
    issues.extend(validate_sources(model))
    issues.extend(validate_catalog_states(model))
    issues.extend(validate_requirements(model))
    packet_ids: set[str] = set()
    for path, packet in model.packets:
        identifier = packet.get("id")
        if identifier in packet_ids:
            issues.append(Issue("duplicate_id", f"task:{identifier}"))
        packet_ids.add(identifier)
        issues.extend(validate_packet(model, path, packet))
    return issues


def documentation_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and ".git" not in path.parts and "__pycache__" not in path.parts
    ]


def validate_content(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in documentation_files(root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        if not text.strip():
            issues.append(Issue("empty_file", relative))
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(Issue("possible_secret", relative))
                break
        if path.suffix != ".md":
            continue
        for target in MARKDOWN_LINK.findall(text):
            target = target.strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            destination = target.split("#", maxsplit=1)[0]
            if not destination:
                continue
            if not (path.parent / destination).is_file():
                issues.append(Issue("broken_markdown_reference", f"{relative}:{destination}"))
    return issues


def print_context(root: Path, task_id: str) -> int:
    model = load_model(root)
    packet_path, packet = next(
        ((path, item) for path, item in model.packets if item.get("id") == task_id), (None, None)
    )
    if packet_path is None or packet is None:
        print(f"ERROR: unknown task {task_id}")
        return 1
    issues = list(model.issues) + validate_profile(model) + validate_packet(model, packet_path, packet)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue.code}: {issue.detail}")
        return 1
    budget = model.profile["context"]["max_words"]
    source_lines = []
    for source in packet["sources"]:
        source_lines.append(f"- {source} | sha256: {model.sources[source_path(source)]} | updated: current")
    decision_lines = [f"- {decision} | {model.decisions[decision]}" for decision in packet["decisions"]]
    requirement_lines = [
        f"- {identifier} | {model.requirements[identifier]['state']}"
        for identifier in packet["requirements"]
    ]
    text = "\n".join(
        [
            f"# {packet['id']}: {packet['objective']}",
            "Sources:\n" + "\n".join(source_lines),
            "Decisions:\n" + "\n".join(decision_lines),
            "Requirements:\n" + "\n".join(requirement_lines),
            f"Scope: {packet['scope']}",
            f"Acceptance: {packet['acceptance']}",
            f"Open decisions: {packet['open_decisions']}",
            f"Blockers: {packet['blockers']}",
            f"Autonomy limits: {packet['autonomy']}",
            f"Limits: {packet['limits']}",
        ]
    )
    if words(text) > budget:
        print("ERROR: rendered context exceeds configured budget")
        return 1
    print(text)
    return 0


def refresh_hashes(root: Path) -> None:
    manifest_path = root / "sources.yaml"
    manifest = read_mapping(manifest_path, []) or {"sources": []}
    for source in manifest.get("sources", []):
        source["sha256"] = digest(resolve(root, source["path"]))
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "context", "hash", "check"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--task")
    args = parser.parse_args()
    if args.command in {"validate", "check"}:
        issues = validate(args.root)
        if args.command == "check":
            issues.extend(validate_content(args.root))
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
