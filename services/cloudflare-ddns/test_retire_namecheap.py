import unittest
from retire_namecheap import without_migrated_blocks


class RetirementTests(unittest.TestCase):
    def test_preserves_other_domains_and_is_idempotent(self):
        global_settings = '#### Global Settings\ndaemon=150\nprotocol=namecheap\n\n'
        other = '#### susabogados.es\nlogin=susabogados.es\npassword=unrelated\n@.susabogados.es\n'
        removed = '#### beachlab.org\nlogin=beachlab.org\npassword=old\n@.beachlab.org, hs.beachlab.org\n\n'
        source = global_settings + removed + other
        result = without_migrated_blocks(source)
        self.assertEqual(result, global_settings + other)
        self.assertEqual(without_migrated_blocks(result), result)

    def test_refuses_mismatched_login(self):
        with self.assertRaises(ValueError):
            without_migrated_blocks('#### hexxan.com\nlogin=unrelated.org\npassword=keep\n')


if __name__ == '__main__':
    unittest.main()
