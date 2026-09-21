from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from harness.spec_harness import print_context, refresh_hashes, validate, validate_content


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal"


class SpecHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "example"
        shutil.copytree(EXAMPLE, self.root)
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
