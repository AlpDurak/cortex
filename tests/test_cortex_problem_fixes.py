import socket
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "cortex.main", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
    )


class CortexProblemFixTests(unittest.TestCase):
    def test_help_exposes_snapshot_and_bootstrap_commands(self):
        result = run_cli(["--help"])

        self.assertEqual(result.returncode, 0)
        self.assertIn("snapshot", result.stdout)
        self.assertIn("Create a graph snapshot", result.stdout)
        self.assertIn("bootstrap", result.stdout)
        self.assertIn("Scan a project and seed a baseline graph", result.stdout)
        self.assertIn("scan", result.stdout)

    def test_run_reports_port_in_use_clearly(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            result = run_cli(["run", "--root", str(ROOT), "--port", str(port)])
        finally:
            sock.close()

        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn(f"port {port} is already in use", combined)
        self.assertIn("cortex run --port", combined)

    def test_hook_reminder_is_suppressed_when_hook_installed(self):
        import tempfile

        temp_root = Path(tempfile.mkdtemp())
        script = """
from pathlib import Path
import cortex.mcp_server as srv
root = Path(r'{root}')
(root / '.git' / 'hooks').mkdir(parents=True)
(root / '.git' / 'hooks' / 'post-commit').write_text('# cortex-hook\\n', encoding='utf-8')
srv.PROJECT_ROOT = root
srv._mgr = None
srv._hook_reminder_shown = False
print(srv.get_graph_timeline())
""".format(root=str(temp_root).replace("\\", "\\\\"))
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("cortex hook install", result.stderr)

    def test_skill_status_vocabulary_matches_runtime(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("proposed", skill)
        self.assertIn("building", skill)
        self.assertIn("shipped", skill)
        self.assertNotIn("planned, in-progress, or done", skill)
        self.assertNotIn('status="planned"', skill)

    def test_bootstrap_command_seeds_baseline_graph(self):
        with self.subTest("bootstrap"):
            self._assert_scan_command_seeds_graph("bootstrap")
        with self.subTest("scan"):
            self._assert_scan_command_seeds_graph("scan")

    def _assert_scan_command_seeds_graph(self, command):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "app.py").write_text("import requests\nprint('hi')\n", encoding="utf-8")

            result = run_cli([command, "--root", str(root), "--message", "test bootstrap"])

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Baseline graph seeded", result.stdout)

            from core.db import DatabaseManager

            mgr = DatabaseManager(root)
            mgr.init()
            try:
                file_count = mgr.query_to_dicts("MATCH (n:File) RETURN count(*) AS c")[0]["c"]
                design_count = mgr.query_to_dicts("MATCH (n:SystemDesign) RETURN count(*) AS c")[0]["c"]
                timeline = mgr.get_timeline()
            finally:
                mgr.close()

            self.assertGreaterEqual(file_count, 2)
            self.assertGreaterEqual(design_count, 1)
            self.assertTrue(any("test bootstrap" in item["message"] for item in timeline))

    def test_commit_snapshot_contract_documents_reacquiring_connection(self):
        from core.db import DatabaseManager

        self.assertIn("Re-acquire", DatabaseManager.commit_snapshot.__doc__)


if __name__ == "__main__":
    unittest.main()
