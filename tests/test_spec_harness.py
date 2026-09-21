from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from harness.spec_harness import (
    build_snapshot,
    close_round,
    load_model,
    print_context,
    print_dashboard,
    refresh_hashes,
    render_dashboard,
    round_records,
    validate,
    validate_content,
)


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal"


class SpecHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "example"
        shutil.copytree(EXAMPLE, self.root)
        shutil.rmtree(self.root / "rounds", ignore_errors=True)
        refresh_hashes(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def codes(self) -> set[str]:
        return {issue.code for issue in validate(self.root)}

    def test_example_is_valid(self):
        self.assertEqual(validate(self.root), [])

    def test_context_renders_current_source_state(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = print_context(self.root, "TASK-001")
        self.assertEqual(result, 0)
        self.assertIn("updated: current", output.getvalue())
        self.assertIn("Autonomy limits:", output.getvalue())

    def test_line_endings_do_not_change_a_text_source_hash(self):
        path = self.root / "sources" / "source.md"
        path.write_bytes(b"\n".join(path.read_bytes().splitlines()) + b"\n")
        self.assertEqual(validate(self.root), [])
    def test_changed_source_requires_review(self):
        path = self.root / "sources" / "source.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        self.assertIn("source_changed", self.codes())
        self.assertIn("evidence_source_changed", self.codes())

    def test_changed_evidence_hash_requires_review(self):
        path = self.root / "evidence.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("source.md: ", "source.md: altered-"), encoding="utf-8")
        self.assertIn("evidence_source_changed", self.codes())

    def test_missing_source_is_rejected(self):
        (self.root / "sources" / "source.md").unlink()
        self.assertIn("missing_source", self.codes())

    def test_orphan_decision_is_rejected(self):
        trace_path = self.root / "traceability.yaml"
        text = trace_path.read_text(encoding="utf-8").replace("decision: ADR-001", "decision: ADR-404", 1)
        trace_path.write_text(text, encoding="utf-8")
        self.assertIn("orphan_decision", self.codes())

    def test_duplicate_requirement_is_rejected(self):
        trace_path = self.root / "traceability.yaml"
        text = trace_path.read_text(encoding="utf-8")
        text += """
  - id: REQ-001
    source: sources/source.md#service-request
    decision: ADR-001
    contract: CON-REQUEST-SCHEDULING
    test: TEST-REQ-001
    evidence: EVD-REQ-001
    state: specified
"""
        trace_path.write_text(text, encoding="utf-8")
        self.assertIn("duplicate_id", self.codes())

    def test_implemented_requirement_requires_executed_chain(self):
        trace = self.root / "traceability.yaml"
        trace.write_text(trace.read_text(encoding="utf-8").replace("state: specified", "state: implemented", 1), encoding="utf-8")
        self.assertIn("unproven_completion", self.codes())

    def test_adulterated_packet_blocks_context_rendering(self):
        packet = self.root / "tasks" / "TASK-001.yaml"
        packet.write_text(packet.read_text(encoding="utf-8").replace("sources/source.md", "sources/missing.md"), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            result = print_context(self.root, "TASK-001")
        self.assertEqual(result, 1)
        self.assertIn("packet_source_invalid", output.getvalue())

    def test_packet_budget_is_enforced(self):
        profile = self.root / "project-profile.yaml"
        profile.write_text(profile.read_text(encoding="utf-8").replace("max_words: 350", "max_words: 100"), encoding="utf-8")
        packet = self.root / "tasks" / "TASK-001.yaml"
        packet.write_text(packet.read_text(encoding="utf-8").replace("Do not create a runtime API or claim executed test evidence.", "word " * 150), encoding="utf-8")
        self.assertIn("packet_over_budget", self.codes())

    def test_content_hygiene_detects_empty_and_broken_reference(self):
        (self.root / "empty.md").write_text("", encoding="utf-8")
        (self.root / "broken.md").write_text("[missing](nope.md)\n", encoding="utf-8")
        codes = {issue.code for issue in validate_content(self.root)}
        self.assertEqual(codes, {"empty_file", "broken_markdown_reference"})

    def test_dashboard_calculates_explicit_progress_and_counts(self):
        snapshot = build_snapshot(load_model(self.root), "TASK-001", [])
        self.assertEqual(snapshot["progress"]["task"]["percent"], 50.0)
        self.assertEqual(snapshot["progress"]["stage"]["total"], 1)
        self.assertEqual(snapshot["progress"]["total"]["total"], 1)
        self.assertEqual(snapshot["task_counts"]["in_progress"], 1)
        self.assertEqual(snapshot["task_counts"]["unknown"], 0)
        self.assertEqual(len(snapshot["gates"]), 3)
        self.assertEqual([item["gate"] for item in snapshot["gates"]], ["especificação", "implementação", "release"])

    def test_aggregate_task_is_not_double_counted(self):
        child = self.root / "tasks" / "TASK-001.yaml"
        child.write_text(child.read_text(encoding="utf-8") + "parent: TASK-GROUP\n", encoding="utf-8")
        group = {
            "id": "TASK-GROUP",
            "objective": "Aggregate the synthetic documentation work.",
            "sources": ["sources/source.md"],
            "decisions": ["ADR-001"],
            "requirements": ["REQ-001"],
            "scope": "Aggregate only.",
            "acceptance": "Child task is complete.",
            "open_decisions": [],
            "blockers": [],
            "autonomy": "No business approval.",
            "limits": "Documentation only.",
            "owner": "fictional documentation team",
            "depends_on": [],
            "status": "pending",
            "stage": "Specification",
        }
        (self.root / "tasks" / "TASK-GROUP.yaml").write_text(
            yaml.safe_dump(group, sort_keys=False), encoding="utf-8"
        )
        self.assertEqual(validate(self.root), [])
        snapshot = build_snapshot(load_model(self.root), "TASK-001", [])
        self.assertEqual(snapshot["progress"]["total"]["total"], 1)
        self.assertEqual(snapshot["task_counts"]["pending"], 1)

    def test_legacy_packet_remains_valid_but_progress_is_unknown(self):
        path = self.root / "tasks" / "TASK-001.yaml"
        packet = yaml.safe_load(path.read_text(encoding="utf-8"))
        for field in ("owner", "depends_on", "status", "stage", "acceptance_criteria", "resume"):
            packet.pop(field, None)
        packet["open_decisions"] = "The fictional notification mechanism remains undecided."
        packet["blockers"] = "No external blocker is recorded."
        path.write_text(yaml.safe_dump(packet, sort_keys=False), encoding="utf-8")
        self.assertEqual(validate(self.root), [])
        snapshot = build_snapshot(load_model(self.root), "TASK-001", [])
        self.assertIsNone(snapshot["progress"]["task"]["percent"])
        self.assertIsNone(snapshot["progress"]["total"]["percent"])
        self.assertEqual(snapshot["task_counts"]["unknown"], 1)

    def test_invalid_task_state_and_unproven_criterion_are_rejected(self):
        path = self.root / "tasks" / "TASK-001.yaml"
        text = path.read_text(encoding="utf-8").replace("status: in_progress", "status: mysterious")
        text = text.replace("evidence: traceability.yaml", "evidence: null")
        path.write_text(text, encoding="utf-8")
        self.assertIn("invalid_task_state", self.codes())
        self.assertIn("unproven_acceptance", self.codes())

    def test_dashboard_query_has_no_filesystem_side_effects(self):
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        output = io.StringIO()
        with redirect_stdout(output):
            result = print_dashboard(self.root, task_id="TASK-001")
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(result, 0)
        self.assertEqual(before, after)
        self.assertIn("50% — 1 de 2 critérios", output.getvalue())

    def test_changed_source_marks_dashboard_unvalidated_and_blocks_closure(self):
        source = self.root / "sources" / "source.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            dashboard_result = print_dashboard(self.root, task_id="TASK-001")
            close_result = close_round(self.root, self.root / "round-input.yaml")
        self.assertEqual(dashboard_result, 1)
        self.assertEqual(close_result, 1)
        self.assertIn("DADOS NÃO VALIDADOS", output.getvalue())
        self.assertIn("cannot be recorded as validated", output.getvalue())

    def test_round_closure_is_idempotent_and_conflicts_are_preserved(self):
        output = io.StringIO()
        with redirect_stdout(output):
            first = close_round(self.root, self.root / "round-input.yaml")
            second = close_round(self.root, self.root / "round-input.yaml")
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(len(round_records(self.root)), 1)
        self.assertIn("already recorded; no changes", output.getvalue())
        input_path = self.root / "round-input.yaml"
        input_path.write_text(
            input_path.read_text(encoding="utf-8").replace("contract approval remains pending", "the scope changed"),
            encoding="utf-8",
        )
        with redirect_stdout(output):
            conflict = close_round(self.root, input_path)
        self.assertEqual(conflict, 1)
        self.assertEqual(len(round_records(self.root)), 1)
        self.assertIn("round_conflict", output.getvalue())

    def test_scope_change_is_explained_in_round_comparison(self):
        self.assertEqual(close_round(self.root, self.root / "round-input.yaml"), 0)
        second_task = yaml.safe_load((self.root / "tasks" / "TASK-001.yaml").read_text(encoding="utf-8"))
        second_task.update(
            {
                "id": "TASK-002",
                "objective": "Document the fictional notification choice.",
                "status": "pending",
                "acceptance_criteria": [{"id": "AC-NOTIFY", "status": "pending"}],
                "resume": {"file": "status.md", "section": "Status"},
            }
        )
        (self.root / "tasks" / "TASK-002.yaml").write_text(
            yaml.safe_dump(second_task, sort_keys=False), encoding="utf-8"
        )
        second_input = yaml.safe_load((self.root / "round-input.yaml").read_text(encoding="utf-8"))
        second_input.update(
            {
                "id": "ROUND-002",
                "date": "2026-01-02",
                "task": "TASK-002",
                "scope_changes": [
                    {"task": "TASK-002", "change": "added", "reason": "Notification documentation entered the approved scope."}
                ],
            }
        )
        second_path = self.root / "round-input-2.yaml"
        second_path.write_text(yaml.safe_dump(second_input, sort_keys=False), encoding="utf-8")
        self.assertEqual(close_round(self.root, second_path), 0)
        records = round_records(self.root)
        rendered = render_dashboard(records[1]["snapshot"], records[1]["input"], records[1]["validation"], records[0])
        self.assertIn("O escopo mudou de 1 para 2 entregas", rendered)
        self.assertIn("Incluídas: TASK-002", rendered)
        self.assertIn("Notification documentation entered the approved scope", rendered)

    def test_undocumented_scope_change_blocks_closure(self):
        self.assertEqual(close_round(self.root, self.root / "round-input.yaml"), 0)
        packet = yaml.safe_load((self.root / "tasks" / "TASK-001.yaml").read_text(encoding="utf-8"))
        packet.update({"id": "TASK-002", "status": "pending"})
        (self.root / "tasks" / "TASK-002.yaml").write_text(
            yaml.safe_dump(packet, sort_keys=False), encoding="utf-8"
        )
        second_input = yaml.safe_load((self.root / "round-input.yaml").read_text(encoding="utf-8"))
        second_input.update({"id": "ROUND-002", "date": "2026-01-02", "task": "TASK-002"})
        second_path = self.root / "round-input-2.yaml"
        second_path.write_text(yaml.safe_dump(second_input, sort_keys=False), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            result = close_round(self.root, second_path)
        self.assertEqual(result, 1)
        self.assertIn("undocumented_scope_change: TASK-002:added", output.getvalue())

    def test_recorded_validation_reports_when_sources_are_newer(self):
        self.assertEqual(close_round(self.root, self.root / "round-input.yaml"), 0)
        source = self.root / "sources" / "source.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nNew source version.\n", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            result = print_dashboard(self.root, round_id="ROUND-001")
        self.assertEqual(result, 0)
        self.assertIn("refere-se a uma versão anterior das fontes", output.getvalue())

    def test_full_dashboard_flow_renders_recorded_validation_and_resume(self):
        self.assertEqual(close_round(self.root, self.root / "round-input.yaml"), 0)
        output = io.StringIO()
        with redirect_stdout(output):
            result = print_dashboard(self.root, round_id="ROUND-001")
        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("Última validação executada: passed", rendered)
        self.assertIn("Retomar em: [status.md](status.md) — seção Status", rendered)
        self.assertIn("Gates independentes", rendered)
