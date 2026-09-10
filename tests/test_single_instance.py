"""Solo la parte sin Qt de single_instance.py: el resto (QLocalServer/
QLocalSocket real) se verifica en scripts/smoke_test.py, igual que el resto
de la integración con el event loop de Qt en este proyecto."""
import unittest

from algor.core.single_instance import server_name


class ServerNameTests(unittest.TestCase):
    def test_includes_given_uid(self):
        self.assertEqual(server_name(uid=1234), "algor-1234")

    def test_different_uids_never_collide(self):
        self.assertNotEqual(server_name(uid=1000), server_name(uid=1001))

    def test_defaults_to_real_uid_when_not_given(self):
        import os
        self.assertEqual(server_name(), server_name(uid=os.getuid()))


if __name__ == '__main__':
    unittest.main()
