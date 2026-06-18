import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from cortex.web_server import _build_app


class WebServerProjectsTests(unittest.TestCase):
    def setUp(self):
        self._a = tempfile.TemporaryDirectory()
        self._b = tempfile.TemporaryDirectory()
        self.app = _build_app(Path(self._a.name))
        self.client = TestClient(self.app)

    def tearDown(self):
        self._a.cleanup(); self._b.cleanup()

    def test_health_lists_primary(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["projects"]), 1)

    def test_register_adds_second_project(self):
        r = self.client.post("/api/projects/register", json={"root": self._b.name})
        self.assertEqual(r.status_code, 200)
        new_id = r.json()["id"]
        listing = self.client.get("/api/projects").json()
        self.assertEqual(len(listing), 2)
        self.assertIn(new_id, [p["id"] for p in listing])

    def test_register_is_idempotent(self):
        first = self.client.post("/api/projects/register", json={"root": self._b.name}).json()["id"]
        second = self.client.post("/api/projects/register", json={"root": self._b.name}).json()["id"]
        self.assertEqual(first, second)
        self.assertEqual(len(self.client.get("/api/projects").json()), 2)

    def test_graph_scoped_to_project(self):
        new_id = self.client.post("/api/projects/register", json={"root": self._b.name}).json()["id"]
        r = self.client.get(f"/api/graph?project={new_id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("nodes", r.json())

    def test_unknown_project_is_404(self):
        r = self.client.get("/api/graph?project=deadbeef")
        self.assertEqual(r.status_code, 404)

    def test_delete_detaches_and_refuses_last(self):
        new_id = self.client.post("/api/projects/register", json={"root": self._b.name}).json()["id"]
        self.assertEqual(self.client.delete(f"/api/projects/{new_id}").status_code, 200)
        self.assertEqual(len(self.client.get("/api/projects").json()), 1)
        primary_id = self.client.get("/api/projects").json()[0]["id"]
        self.assertEqual(self.client.delete(f"/api/projects/{primary_id}").status_code, 409)


if __name__ == "__main__":
    unittest.main()
