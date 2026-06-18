import tempfile, unittest
from pathlib import Path
from cortex.registry import Registry, project_id


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._a = tempfile.TemporaryDirectory()
        self._b = tempfile.TemporaryDirectory()
        self.a = Path(self._a.name)
        self.b = Path(self._b.name)
        self.reg = Registry()

    def tearDown(self):
        for st in self.reg.list():
            try: st.mgr.close()
            except Exception: pass
        self._a.cleanup(); self._b.cleanup()

    def test_project_id_stable_and_short(self):
        self.assertEqual(project_id(self.a), project_id(self.a))
        self.assertEqual(len(project_id(self.a)), 8)
        self.assertNotEqual(project_id(self.a), project_id(self.b))

    def test_register_is_idempotent(self):
        s1 = self.reg.register(self.a)
        s2 = self.reg.register(self.a)
        self.assertIs(s1, s2)
        self.assertEqual(len(self.reg.list()), 1)

    def test_first_registered_is_primary(self):
        s1 = self.reg.register(self.a)
        self.reg.register(self.b)
        self.assertIs(self.reg.primary, s1)

    def test_remove_closes_and_drops(self):
        self.reg.register(self.a)
        sb = self.reg.register(self.b)
        self.assertTrue(self.reg.remove(sb.id))
        self.assertIsNone(self.reg.get(sb.id))
        self.assertEqual(len(self.reg.list()), 1)

    def test_remove_refuses_last(self):
        sa = self.reg.register(self.a)
        self.assertFalse(self.reg.remove(sa.id))
        self.assertEqual(len(self.reg.list()), 1)


if __name__ == "__main__":
    unittest.main()
