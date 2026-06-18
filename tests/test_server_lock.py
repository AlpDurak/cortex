import tempfile, unittest
from pathlib import Path
from cortex import server_lock


class ServerLockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "server.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_and_clear(self):
        server_lock.write_lock("127.0.0.1", 7842, path=self.path)
        lock = server_lock.read_lock(path=self.path)
        self.assertEqual(lock["host"], "127.0.0.1")
        self.assertEqual(lock["port"], 7842)
        self.assertIn("pid", lock)
        server_lock.clear_lock(path=self.path)
        self.assertIsNone(server_lock.read_lock(path=self.path))

    def test_decide_start_when_no_lock(self):
        self.assertEqual(server_lock.decide(None, lambda h, p: None), "start")

    def test_decide_attach_when_server_alive(self):
        lock = {"host": "127.0.0.1", "port": 7842}
        probe = lambda h, p: {"status": "ok"}
        self.assertEqual(server_lock.decide(lock, probe), "attach")

    def test_decide_start_when_server_dead(self):
        lock = {"host": "127.0.0.1", "port": 7842}
        probe = lambda h, p: None
        self.assertEqual(server_lock.decide(lock, probe), "start")


if __name__ == "__main__":
    unittest.main()
