from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from harness.spec_harness import refresh_hashes, validate


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal"


class SpecHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "example"
        shutil.copytree(EXAMPLE, self.root)
        refresh_hashes(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_example_is_valid(self):
        self.assertEqual(validate(self.root), [])

    def test_changed_source_requires_review(self):
        path = self.root / "sources" / "source.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        self.assertTrue(any(issue.code == "source_changed" for issue in validate(self.root)))

    def test_implemented_requirement_requires_executed_evidence(self):
        trace = self.root / "traceability.yaml"
        text = trace.read_text(encoding="utf-8").replace("state: specified", "state: implemented")
        trace.write_text(text, encoding="utf-8")
        self.assertTrue(any(issue.code == "unproven_completion" for issue in validate(self.root)))

    def test_packet_budget_is_enforced(self):
        profile = self.root / "project-profile.yaml"
        profile.write_text(profile.read_text(encoding="utf-8").replace("max_words: 350", "max_words: 100"), encoding="utf-8")
        packet = self.root / "tasks" / "TASK-001.yaml"
        packet.write_text(
            packet.read_text(encoding="utf-8").replace(
                "Do not create a runtime API or claim executed test evidence.", "word " * 150
            ),
            encoding="utf-8",
        )
        self.assertTrue(any(issue.code == "packet_over_budget" for issue in validate(self.root)))
