import tempfile
import unittest
from pathlib import Path

from core.agent_instructions import (
    CORTEX_MARKER,
    write_agent_instructions,
)


class WriteAgentInstructionsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_both_files_when_missing(self):
        result = write_agent_instructions(self.root)

        self.assertEqual(set(result["written"]), {"CLAUDE.md", "AGENTS.md"})
        self.assertEqual(result["skipped"], [])
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (self.root / name).read_text(encoding="utf-8")
            self.assertIn(CORTEX_MARKER, text)

    def test_appends_to_bottom_preserving_existing_content(self):
        existing = "# My Project\n\nSome existing rules here.\n"
        (self.root / "CLAUDE.md").write_text(existing, encoding="utf-8")

        result = write_agent_instructions(self.root)

        text = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        # Existing content is kept, and the Cortex section is at the bottom.
        self.assertTrue(text.startswith("# My Project"))
        self.assertIn("Some existing rules here.", text)
        self.assertIn(CORTEX_MARKER, text)
        self.assertLess(text.index("Some existing rules here."), text.index(CORTEX_MARKER))
        self.assertIn("CLAUDE.md", result["written"])

    def test_idempotent_when_marker_already_present(self):
        write_agent_instructions(self.root)
        result = write_agent_instructions(self.root)

        self.assertEqual(result["written"], [])
        self.assertEqual(set(result["skipped"]), {"CLAUDE.md", "AGENTS.md"})
        # No duplicated section.
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(CORTEX_MARKER), 1)


if __name__ == "__main__":
    unittest.main()
