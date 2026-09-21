"""Validate concise, evidence-based specification artifacts."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import date
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
TASK_STATES = {"completed", "in_progress", "pending", "blocked", "cancelled"}
ACCEPTANCE_STATES = {"met", "pending", "not_applicable"}
ROUND_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
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


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def digest(path: Path) -> str:
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(content).hexdigest()
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


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
    issues: list[Issue] = []
    budget = model.profile.get("context", {}).get("max_words")
    if not isinstance(budget, int) or budget < 100:
        issues.append(Issue("invalid_budget", "project-profile.yaml context.max_words must be an integer >= 100"))
    dashboard = model.profile.get("dashboard")
    if dashboard is not None and (
        not isinstance(dashboard, dict) or not isinstance(dashboard.get("scope_complete"), bool)
    ):
        issues.append(Issue("invalid_dashboard_config", "project-profile.yaml dashboard.scope_complete must be boolean"))
    return issues


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


def validate_dashboard_fields(model: Model) -> list[Issue]:
    """Validate optional structured task fields without breaking legacy packets."""
    issues: list[Issue] = []
    task_ids = {packet.get("id") for _, packet in model.packets if isinstance(packet.get("id"), str)}
    parent_ids = {packet.get("parent") for _, packet in model.packets if isinstance(packet.get("parent"), str)}
    for path, packet in model.packets:
        identifier = packet.get("id", path.stem)
        state = packet.get("status")
        if state is not None and state not in TASK_STATES:
            issues.append(Issue("invalid_task_state", f"{identifier}:{state}"))
        for field in ("owner", "stage"):
            if field in packet and (not isinstance(packet[field], str) or not packet[field].strip()):
                issues.append(Issue("invalid_task_field", f"{identifier}:{field}"))
        dependencies = packet.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            issues.append(Issue("invalid_task_dependencies", str(identifier)))
        else:
            for dependency in dependencies:
                if dependency not in task_ids or dependency == identifier:
                    issues.append(Issue("orphan_task_dependency", f"{identifier}:{dependency}"))
        parent = packet.get("parent")
        if parent is not None and (not isinstance(parent, str) or parent not in task_ids or parent == identifier):
            issues.append(Issue("orphan_task_parent", f"{identifier}:{parent}"))
        criteria = packet.get("acceptance_criteria")
        if criteria is not None:
            if not isinstance(criteria, list) or not all(isinstance(item, dict) for item in criteria):
                issues.append(Issue("invalid_acceptance_criteria", str(identifier)))
            else:
                criterion_ids: set[str] = set()
                for criterion in criteria:
                    criterion_id = criterion.get("id")
                    criterion_state = criterion.get("status")
                    if not isinstance(criterion_id, str) or not criterion_id:
                        issues.append(Issue("invalid_acceptance_criterion", f"{identifier}:missing_id"))
                    elif criterion_id in criterion_ids:
                        issues.append(Issue("duplicate_id", f"criterion:{identifier}:{criterion_id}"))
                    criterion_ids.add(criterion_id)
                    if criterion_state not in ACCEPTANCE_STATES:
                        issues.append(Issue("invalid_acceptance_state", f"{identifier}:{criterion_id}"))
                    if criterion_state == "met" and not isinstance(criterion.get("evidence"), str):
                        issues.append(Issue("unproven_acceptance", f"{identifier}:{criterion_id}"))
                    elif criterion_state == "met":
                        try:
                            if not resolve(model.root, criterion["evidence"]).is_file():
                                issues.append(Issue("missing_acceptance_evidence", f"{identifier}:{criterion_id}"))
                        except ValueError:
                            issues.append(Issue("invalid_path", criterion["evidence"]))
                if state == "completed" and any(item.get("status") == "pending" for item in criteria):
                    issues.append(Issue("inconsistent_task_completion", str(identifier)))
                if state == "completed" and not criteria:
                    issues.append(Issue("unproven_task_completion", str(identifier)))
        elif state == "completed":
            issues.append(Issue("unproven_task_completion", str(identifier)))
        blockers = packet.get("blockers")
        if isinstance(blockers, list):
            for index, blocker in enumerate(blockers, start=1):
                if not isinstance(blocker, dict) or not isinstance(blocker.get("reason"), str):
                    issues.append(Issue("invalid_blocker", f"{identifier}:{index}"))
                    continue
                if "owner" in blocker and not isinstance(blocker["owner"], str):
                    issues.append(Issue("invalid_blocker", f"{identifier}:{index}:owner"))
                affected = blocker.get("affects", [])
                if not isinstance(affected, list) or not all(isinstance(item, str) for item in affected):
                    issues.append(Issue("invalid_blocker", f"{identifier}:{index}:affects"))
                else:
                    for affected_task in affected:
                        if affected_task not in task_ids:
                            issues.append(Issue("orphan_blocked_task", f"{identifier}:{affected_task}"))
            if blockers and state != "blocked":
                issues.append(Issue("inconsistent_task_blockers", str(identifier)))
        elif blockers is not None and not isinstance(blockers, str):
            issues.append(Issue("invalid_blockers", str(identifier)))
        if state == "blocked" and (not blockers or (isinstance(blockers, str) and not blockers.strip())):
            issues.append(Issue("missing_task_blocker", str(identifier)))
        open_decisions = packet.get("open_decisions")
        if isinstance(open_decisions, list):
            for index, decision in enumerate(open_decisions, start=1):
                if not isinstance(decision, dict) or not isinstance(decision.get("action"), str):
                    issues.append(Issue("invalid_open_decision", f"{identifier}:{index}"))
        elif open_decisions is not None and not isinstance(open_decisions, str):
            issues.append(Issue("invalid_open_decisions", str(identifier)))
        resume = packet.get("resume")
        if resume is not None:
            if not isinstance(resume, dict) or not isinstance(resume.get("file"), str):
                issues.append(Issue("invalid_resume", str(identifier)))
            else:
                try:
                    if not resolve(model.root, resume["file"]).is_file():
                        issues.append(Issue("missing_resume_file", f"{identifier}:{resume['file']}"))
                except ValueError:
                    issues.append(Issue("invalid_path", resume["file"]))
    for parent_id in parent_ids:
        if parent_id not in task_ids:
            issues.append(Issue("orphan_task_parent", str(parent_id)))
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
    issues.extend(validate_dashboard_fields(model))
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


def source_version(model: Model) -> str:
    parts = []
    for path_text in sorted(model.sources):
        try:
            path = resolve(model.root, path_text)
            actual = digest(path) if path.is_file() else "missing"
        except ValueError:
            actual = "invalid"
        parts.append(f"{path_text}:{model.sources[path_text]}:{actual}")
    serialized = "\n".join(parts)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def progress_metric(completed: int, total: int, provisional: bool = False) -> dict[str, Any]:
    if total <= 0:
        return {"completed": completed, "total": total, "percent": None, "provisional": provisional}
    return {
        "completed": completed,
        "total": total,
        "percent": round(completed * 100 / total, 1),
        "provisional": provisional,
    }


def packet_index(model: Model) -> dict[str, tuple[Path, dict[str, Any]]]:
    return {
        packet["id"]: (path, packet)
        for path, packet in model.packets
        if isinstance(packet.get("id"), str)
    }


def leaf_packets(model: Model) -> list[tuple[Path, dict[str, Any]]]:
    parents = {packet.get("parent") for _, packet in model.packets if isinstance(packet.get("parent"), str)}
    return [item for item in model.packets if item[1].get("id") not in parents]


def task_counts(model: Model) -> dict[str, int]:
    counts = {state: 0 for state in sorted(TASK_STATES)}
    counts["unknown"] = 0
    for _, packet in model.packets:
        state = packet.get("status")
        counts[state if state in TASK_STATES else "unknown"] += 1
    return counts


def acceptance_progress(packet: dict[str, Any]) -> dict[str, Any]:
    criteria = packet.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return progress_metric(0, 0)
    applicable = [item for item in criteria if item.get("status") != "not_applicable"]
    return progress_metric(sum(item.get("status") == "met" for item in applicable), len(applicable))


def delivery_progress(
    packets: list[tuple[Path, dict[str, Any]]], provisional: bool
) -> dict[str, Any]:
    included = [packet for _, packet in packets if packet.get("status") in TASK_STATES - {"cancelled"}]
    return progress_metric(sum(packet.get("status") == "completed" for packet in included), len(included), provisional)


def source_review_items(model: Model, issues: list[Issue]) -> list[dict[str, Any]]:
    affected_paths = sorted(
        {
            issue.detail.split(":")[-1]
            for issue in issues
            if issue.code in {"source_changed", "missing_source", "evidence_source_changed"}
        }
    )
    review: list[dict[str, Any]] = []
    for path_text in affected_paths:
        affected_requirements = sorted(
            identifier
            for identifier, requirement in model.requirements.items()
            if source_path(str(requirement.get("source", ""))) == path_text
        )
        affected_tasks = sorted(
            packet.get("id")
            for _, packet in model.packets
            if path_text in [source_path(str(item)) for item in packet.get("sources", [])]
        )
        review.append(
            {"path": path_text, "requirements": affected_requirements, "tasks": affected_tasks}
        )
    return review


def blocker_items(model: Model) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for _, packet in model.packets:
        blockers = packet.get("blockers")
        if isinstance(blockers, list):
            for blocker in blockers:
                if isinstance(blocker, dict):
                    result.append(
                        {
                            "task": packet.get("id"),
                            "reason": blocker.get("reason", "não informado"),
                            "owner": blocker.get("owner", packet.get("owner", "não informado")),
                            "affects": blocker.get("affects", []),
                        }
                    )
        elif packet.get("status") == "blocked" and isinstance(blockers, str):
            result.append(
                {
                    "task": packet.get("id"),
                    "reason": blockers,
                    "owner": packet.get("owner", "não informado"),
                    "affects": [],
                }
            )
    return result


def user_action_items(packet: dict[str, Any]) -> list[dict[str, str]]:
    decisions = packet.get("open_decisions")
    if isinstance(decisions, list):
        return [
            {
                "action": str(item.get("action", "não informado")),
                "owner": str(item.get("owner", "não informado")),
                "impact": str(item.get("impact", "não informado")),
            }
            for item in decisions
            if isinstance(item, dict)
        ]
    if isinstance(decisions, str) and decisions.strip():
        return [{"action": decisions, "owner": "não informado", "impact": "não informado"}]
    return []


def next_action_items(model: Model, current_task: str) -> list[dict[str, str]]:
    indexed = packet_index(model)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for _, packet in leaf_packets(model):
        identifier = str(packet.get("id", ""))
        state = packet.get("status")
        dependencies = packet.get("depends_on", []) if isinstance(packet.get("depends_on", []), list) else []
        unmet = [
            dependency
            for dependency in dependencies
            if dependency in indexed and indexed[dependency][1].get("status") != "completed"
        ]
        if state == "in_progress":
            priority = 0 if identifier == current_task else 1
            reason = "tarefa em andamento"
        elif state == "pending" and not unmet:
            priority = 2
            reason = "dependências concluídas"
        elif state == "pending":
            priority = 3
            reason = "aguarda " + ", ".join(unmet)
        elif state == "blocked":
            priority = 4
            reason = "remover o bloqueio registrado"
        else:
            continue
        candidates.append((priority, identifier, {"task": identifier, "action": str(packet.get("objective", identifier)), "reason": reason}))
    return [item for _, _, item in sorted(candidates, key=lambda value: (value[0], value[1]))[:3]]


def gate_items(model: Model) -> list[dict[str, str]]:
    policies = model.profile.get("gates", {}) if isinstance(model.profile.get("gates"), dict) else {}
    states = {state: 0 for state in sorted(REQUIREMENT_STATES)}
    for requirement in model.requirements.values():
        state = requirement.get("state")
        if state in states:
            states[state] += 1
    return [
        {
            "gate": "especificação",
            "evidence": f"{states['specified']} specified; decisões e fontes são verificadas separadamente",
            "policy": str(policies.get("specification", "não informada")),
        },
        {
            "gate": "implementação",
            "evidence": f"{states['implementation_ready']} implementation_ready; {states['implemented']} implemented",
            "policy": str(policies.get("implementation", "não informada")),
        },
        {
            "gate": "release",
            "evidence": f"{states['released']} released",
            "policy": str(policies.get("release", "não informada")),
        },
    ]


def build_snapshot(model: Model, task_id: str, validation_issues: list[Issue]) -> dict[str, Any]:
    indexed = packet_index(model)
    if task_id not in indexed:
        raise ValueError(f"unknown task {task_id}")
    task_path, packet = indexed[task_id]
    leaves = leaf_packets(model)
    counts = task_counts(model)
    dashboard_config = model.profile.get("dashboard", {})
    scope_complete = isinstance(dashboard_config, dict) and dashboard_config.get("scope_complete") is True
    provisional = not scope_complete or counts["unknown"] > 0
    stage = packet.get("stage")
    stage_packets = [item for item in leaves if stage is not None and item[1].get("stage") == stage]
    return {
        "project": model.profile.get("project", "não informado"),
        "task": task_id,
        "task_path": relative_path(model.root, task_path),
        "stage": stage or "não informado",
        "source_version": source_version(model),
        "validated": not validation_issues,
        "validation_issues": [f"{issue.code}: {issue.detail}" for issue in validation_issues],
        "progress": {
            "task": acceptance_progress(packet),
            "stage": delivery_progress(stage_packets, provisional) if stage is not None else progress_metric(0, 0, True),
            "total": delivery_progress(leaves, provisional),
        },
        "task_counts": counts,
        "scope_ids": sorted(
            str(item.get("id"))
            for _, item in leaves
            if item.get("status") in TASK_STATES - {"cancelled"}
        ),
        "cancelled_ids": sorted(
            str(item.get("id")) for _, item in leaves if item.get("status") == "cancelled"
        ),
        "blockers": blocker_items(model),
        "user_actions": user_action_items(packet),
        "source_review": source_review_items(model, validation_issues),
        "next_actions": next_action_items(model, task_id),
        "resume": packet.get("resume") if isinstance(packet.get("resume"), dict) else {},
        "gates": gate_items(model),
    }


def read_round_input(path: Path) -> tuple[dict[str, Any], list[Issue]]:
    issues: list[Issue] = []
    value = read_mapping(path, issues)
    required = {"id", "date", "task", "summary", "documents_changed", "decisions_recorded"}
    for field in sorted(required - set(value)):
        issues.append(Issue("round_missing", field))
    identifier = value.get("id")
    if not isinstance(identifier, str) or not ROUND_ID.fullmatch(identifier):
        issues.append(Issue("invalid_round_id", str(identifier)))
    try:
        date.fromisoformat(str(value.get("date")))
    except ValueError:
        issues.append(Issue("invalid_round_date", str(value.get("date"))))
    if not isinstance(value.get("task"), str):
        issues.append(Issue("invalid_round_task", str(value.get("task"))))
    if not isinstance(value.get("summary"), str) or not value.get("summary", "").strip():
        issues.append(Issue("invalid_round_summary", "summary"))
    for field in ("documents_changed", "decisions_recorded"):
        if not isinstance(value.get(field), list) or not all(isinstance(item, str) for item in value.get(field, [])):
            issues.append(Issue("invalid_round_field", field))
    scope_changes = value.get("scope_changes", [])
    if not isinstance(scope_changes, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("task"), str)
        and item.get("change") in {"added", "removed", "cancelled"}
        and isinstance(item.get("reason"), str)
        and item.get("reason", "").strip()
        for item in scope_changes
    ):
        issues.append(Issue("invalid_scope_changes", "scope_changes"))
        scope_changes = []
    normalized = {field: value.get(field) for field in ("id", "date", "task", "summary", "documents_changed", "decisions_recorded")}
    normalized["scope_changes"] = scope_changes
    return normalized, issues


def round_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    directory = root / "rounds"
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.yaml")):
        value = read_mapping(path, [])
        if isinstance(value.get("input"), dict) and isinstance(value.get("snapshot"), dict):
            records.append(value)
    return sorted(records, key=lambda item: (str(item["input"].get("date", "")), str(item["input"].get("id", ""))))


def previous_round(records: list[dict[str, Any]], current_id: str | None = None) -> dict[str, Any] | None:
    if current_id is None:
        return records[-1] if records else None
    prior: dict[str, Any] | None = None
    for record in records:
        if record["input"].get("id") == current_id:
            return prior
        prior = record
    return None


def format_metric(metric: dict[str, Any], trusted: bool, unit: str = "entregas") -> str:
    if metric.get("percent") is None:
        text = "não calculável — denominador estruturado indisponível"
    else:
        percent = f"{metric['percent']:g}%"
        text = f"{percent} — {metric['completed']} de {metric['total']} {unit}"
        if metric.get("provisional"):
            text += " (provisório)"
    if not trusted:
        text += " [não validado]"
    return text


def render_dashboard(
    snapshot: dict[str, Any],
    round_input: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    prior: dict[str, Any] | None,
) -> str:
    round_input = round_input or {}
    trusted = bool(snapshot.get("validated"))
    lines = [
        f"# Fechamento da rodada {round_input.get('id', 'não informado')}",
        "",
    ]
    if not trusted:
        lines.extend(["> **DADOS NÃO VALIDADOS.** Corrija as inconsistências antes de registrar um fechamento validado.", ""])
    lines.extend(
        [
            f"- Projeto: {snapshot.get('project', 'não informado')}",
            f"- Data: {round_input.get('date', 'não informada')}",
            f"- Versão das fontes: `{snapshot.get('source_version', 'não informada')}`",
            f"- Localização: etapa **{snapshot.get('stage', 'não informado')}** · tarefa [{snapshot.get('task', 'não informada')}]({snapshot.get('task_path', '')})",
            "",
            "## Resultado da rodada",
            "",
            round_input.get("summary", "não informado"),
            "",
            "## Progresso",
            "",
            "| Escopo | Avanço |",
            "|---|---|",
            f"| Tarefa atual | {format_metric(snapshot['progress']['task'], trusted, 'critérios')} |",
            f"| Etapa | {format_metric(snapshot['progress']['stage'], trusted)} |",
            f"| Documentação total | {format_metric(snapshot['progress']['total'], trusted)} |",
            "",
        ]
    )
    counts = snapshot["task_counts"]
    lines.append(
        "**Tarefas:** "
        f"{counts.get('completed', 0)} concluídas · {counts.get('in_progress', 0)} em andamento · "
        f"{counts.get('pending', 0)} pendentes · {counts.get('blocked', 0)} bloqueadas · "
        f"{counts.get('unknown', 0)} sem estado · {counts.get('cancelled', 0)} canceladas"
    )
    lines.extend(["", "## Comparação com a rodada anterior", ""])
    if prior is None:
        lines.append("Não há rodada anterior registrada.")
    else:
        old = prior["snapshot"]
        old_ids, new_ids = set(old.get("scope_ids", [])), set(snapshot.get("scope_ids", []))
        if old_ids == new_ids:
            old_percent = old.get("progress", {}).get("total", {}).get("percent")
            new_percent = snapshot.get("progress", {}).get("total", {}).get("percent")
            if old_percent is None or new_percent is None:
                lines.append("Base comparável, mas o percentual não é calculável.")
            else:
                lines.append(f"Base comparável: avanço de {new_percent - old_percent:+g} pontos percentuais.")
        else:
            additions, removals = sorted(new_ids - old_ids), sorted(old_ids - new_ids)
            lines.append(
                f"O escopo mudou de {len(old_ids)} para {len(new_ids)} entregas; a diferença percentual não representa somente produtividade."
            )
            lines.append(f"- Incluídas: {', '.join(additions) if additions else 'nenhuma'}")
            lines.append(f"- Removidas: {', '.join(removals) if removals else 'nenhuma'}")
            reasons = {
                (item.get("task"), item.get("change")): item.get("reason")
                for item in round_input.get("scope_changes", [])
                if isinstance(item, dict)
            }
            for identifier in additions:
                lines.append(f"- Motivo de inclusão de {identifier}: {reasons.get((identifier, 'added'), 'não informado')}")
            for identifier in removals:
                reason = reasons.get((identifier, "removed"), reasons.get((identifier, "cancelled"), "não informado"))
                lines.append(f"- Motivo de remoção de {identifier}: {reason}")
    lines.extend(["", "## Bloqueios e ações do usuário", ""])
    if snapshot["blockers"]:
        for item in snapshot["blockers"]:
            affected = ", ".join(item.get("affects", [])) or "não informado"
            lines.append(f"- **{item['task']}**: {item['reason']} · responsável: {item['owner']} · afeta: {affected}")
    else:
        lines.append("- Bloqueios: nenhum registrado.")
    if snapshot["user_actions"]:
        for item in snapshot["user_actions"]:
            lines.append(f"- Decisão: {item['action']} · responsável: {item['owner']} · impacto: {item['impact']}")
    else:
        lines.append("- Decisões do usuário: nenhuma registrada.")
    lines.extend(["", "## Fontes e validação", ""])
    if snapshot["source_review"]:
        for item in snapshot["source_review"]:
            lines.append(
                f"- Revisar `{item['path']}` · requisitos: {', '.join(item['requirements']) or 'não informados'} · tarefas: {', '.join(item['tasks']) or 'não informadas'}"
            )
    else:
        lines.append("- Fontes que exigem revisão: nenhuma detectada.")
    if validation:
        validation_text = f"- Última validação executada: {validation.get('status', 'não informada')} em {validation.get('executed_on', 'não informado')} · `{validation.get('command', 'não informado')}`"
        if validation.get("current_source_version") and validation.get("source_version") != validation.get("current_source_version"):
            validation_text += " · refere-se a uma versão anterior das fontes"
        lines.append(validation_text)
    else:
        lines.append("- Última validação executada: não informada; esta visualização não registra execução.")
    lines.extend(["", "## Gates independentes", "", "| Gate | Evidência registrada | Política |", "|---|---|---|"])
    for gate in snapshot["gates"]:
        lines.append(f"| {gate['gate']} | {gate['evidence']} | {gate['policy']} |")
    lines.extend(["", "## Continuidade", ""])
    if snapshot["next_actions"]:
        for index, item in enumerate(snapshot["next_actions"], start=1):
            lines.append(f"{index}. **{item['task']}** — {item['action']} ({item['reason']}).")
    else:
        lines.append("Nenhuma próxima ação derivável dos estados estruturados.")
    resume = snapshot.get("resume", {})
    if resume:
        section = f" — seção {resume['section']}" if resume.get("section") else ""
        lines.extend(["", f"Retomar em: [{resume['file']}]({resume['file']}){section}."])
    else:
        lines.extend(["", "Ponto de retomada: não informado."])
    documents = round_input.get("documents_changed", [])
    decisions = round_input.get("decisions_recorded", [])
    lines.extend(["", "## Referências da rodada", ""])
    lines.append("- Documentos alterados: " + (", ".join(f"[{item}]({item})" for item in documents) if documents else "nenhum informado"))
    lines.append("- Decisões registradas: " + (", ".join(decisions) if decisions else "nenhuma informada"))
    return "\n".join(lines) + "\n"


def print_dashboard(root: Path, task_id: str = "", round_id: str = "", round_file: Path | None = None) -> int:
    model = load_model(root)
    records = round_records(root)
    if round_id:
        record = next((item for item in records if item["input"].get("id") == round_id), None)
        if record is None:
            print(f"ERROR: unknown round {round_id}")
            return 1
        validation = dict(record.get("validation", {}))
        validation["current_source_version"] = source_version(model)
        print(render_dashboard(record["snapshot"], record["input"], validation, previous_round(records, round_id)), end="")
        return 0
    round_input: dict[str, Any] | None = None
    input_issues: list[Issue] = []
    if round_file is not None:
        round_input, input_issues = read_round_input(round_file)
        task_id = str(round_input.get("task", task_id))
    if not task_id:
        print("ERROR: --task or --round-file is required")
        return 1
    validation_issues = validate(root) + validate_content(root)
    try:
        snapshot = build_snapshot(model, task_id, validation_issues)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1
    print(render_dashboard(snapshot, round_input, None, previous_round(records)), end="")
    for issue in input_issues:
        print(f"ERROR: {issue.code}: {issue.detail}")
    return int(bool(input_issues or validation_issues))


def close_round(root: Path, round_file: Path) -> int:
    round_input, input_issues = read_round_input(round_file)
    if input_issues:
        for issue in input_issues:
            print(f"ERROR: {issue.code}: {issue.detail}")
        return 1
    model = load_model(root)
    if round_input["task"] not in packet_index(model):
        print(f"ERROR: unknown task {round_input['task']}")
        return 1
    for document in round_input["documents_changed"]:
        try:
            if not resolve(root, document).is_file():
                print(f"ERROR: missing round document: {document}")
                return 1
        except ValueError:
            print(f"ERROR: invalid_path: {document}")
            return 1
    for decision in round_input["decisions_recorded"]:
        if decision not in model.decisions:
            print(f"ERROR: unknown round decision: {decision}")
            return 1
    directory = root / "rounds"
    target = directory / f"{round_input['id']}.yaml"
    if target.is_file():
        existing = read_mapping(target, [])
        if existing.get("input") == round_input:
            print(f"OK: round {round_input['id']} already recorded; no changes")
            return 0
        print(f"ERROR: round_conflict: {round_input['id']} already exists with different data")
        return 1
    validation_issues = validate(root) + validate_content(root)
    if validation_issues:
        for issue in validation_issues:
            print(f"ERROR: {issue.code}: {issue.detail}")
        print("BLOCK: invalid or stale project state cannot be recorded as validated")
        return 1
    snapshot = build_snapshot(model, round_input["task"], [])
    prior = previous_round(round_records(root))
    if prior is not None:
        old_ids = set(prior["snapshot"].get("scope_ids", []))
        new_ids = set(snapshot.get("scope_ids", []))
        declared = {(item["task"], item["change"]) for item in round_input["scope_changes"]}
        missing_changes = [
            (identifier, "added") for identifier in sorted(new_ids - old_ids)
            if (identifier, "added") not in declared
        ] + [
            (identifier, "removed") for identifier in sorted(old_ids - new_ids)
            if (identifier, "removed") not in declared and (identifier, "cancelled") not in declared
        ]
        if missing_changes:
            for identifier, change in missing_changes:
                print(f"ERROR: undocumented_scope_change: {identifier}:{change}")
            return 1
    declared_cancelled = {
        item["task"] for item in round_input["scope_changes"] if item["change"] == "cancelled"
    }
    missing_cancelled = set(snapshot.get("cancelled_ids", [])) - declared_cancelled
    if missing_cancelled:
        for identifier in sorted(missing_cancelled):
            print(f"ERROR: undocumented_scope_change: {identifier}:cancelled")
        return 1
    record = {
        "input": round_input,
        "validation": {
            "status": "passed",
            "executed_on": date.today().isoformat(),
            "command": f'python -m harness.spec_harness check --root "{root.as_posix()}"',
            "source_version": snapshot["source_version"],
        },
        "snapshot": snapshot,
    }
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"OK: round {round_input['id']} recorded in {target.as_posix()}")
    return 0


def refresh_hashes(root: Path) -> None:
    manifest_path = root / "sources.yaml"
    manifest = read_mapping(manifest_path, []) or {"sources": []}
    for source in manifest.get("sources", []):
        source["sha256"] = digest(resolve(root, source["path"]))
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "context", "hash", "check", "dashboard", "close-round"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--task")
    parser.add_argument("--round")
    parser.add_argument("--round-file", type=Path)
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
    if args.command == "dashboard":
        return print_dashboard(args.root, args.task or "", args.round or "", args.round_file)
    if args.command == "close-round":
        if args.round_file is None:
            parser.error("close-round requires --round-file")
        return close_round(args.root, args.round_file)
    refresh_hashes(args.root)
    print("OK: source hashes refreshed; assess impact before accepting source changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
