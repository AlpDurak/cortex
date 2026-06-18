# tests/test_run_flow.py
import argparse, unittest
from unittest import mock
from pathlib import Path
import tempfile
import cortex.main as main


class RunFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _args(self):
        return argparse.Namespace(root=self.root, host="127.0.0.1", port=7842)

    def test_attaches_when_server_alive(self):
        args = self._args()
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = b'{"id": "abcd1234", "name": "proj"}'
        fake_resp.__enter__.return_value = fake_resp
        with mock.patch("cortex.server_lock.read_lock", return_value={"host": "127.0.0.1", "port": 7842}), \
             mock.patch("cortex.server_lock.decide", return_value="attach"), \
             mock.patch("urllib.request.urlopen", return_value=fake_resp) as urlopen, \
             mock.patch("webbrowser.open") as wb, \
             mock.patch("uvicorn.run") as uv:
            main._cmd_run(args)
        self.assertTrue(urlopen.called)   # registered with the running server
        self.assertTrue(wb.called)        # opened the browser
        self.assertFalse(uv.called)       # did NOT start a second server

    def test_starts_server_when_none_running(self):
        args = self._args()
        with mock.patch("cortex.server_lock.read_lock", return_value=None), \
             mock.patch("cortex.server_lock.decide", return_value="start"), \
             mock.patch("cortex.main._port_available", return_value=True), \
             mock.patch("cortex.server_lock.write_lock") as wl, \
             mock.patch("cortex.server_lock.clear_lock"), \
             mock.patch("cortex.web_server._build_app", return_value=object()), \
             mock.patch("uvicorn.run") as uv:
            main._cmd_run(args)
        self.assertTrue(wl.called)        # wrote the lockfile
        self.assertTrue(uv.called)        # started the server


if __name__ == "__main__":
    unittest.main()
