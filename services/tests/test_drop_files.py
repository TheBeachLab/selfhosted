import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('drop', Path(__file__).parents[1] / 'drop.py')
drop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drop)

class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        drop.FILES_DIR = self.root / 'downloads'
        drop.FILES_DIR.mkdir()
        self.outside = self.root / 'private'
        self.outside.mkdir()
        (self.outside / 'secret').write_text('private')

    def test_navigation_and_recursive_delete_never_follow_links(self):
        folder = drop.FILES_DIR / 'Carpeta ñ'
        folder.mkdir()
        (folder / 'file.txt').write_text('ok')
        (folder / 'escape').symlink_to(self.outside, target_is_directory=True)
        self.assertEqual([x['name'] for x in drop.listing('Carpeta ñ')], ['file.txt'])
        with self.assertRaises(OSError):
            drop.listing('Carpeta ñ/escape')
        with self.assertRaises(OSError):
            drop.delete_file('Carpeta ñ/escape/secret')
        drop.delete_file('Carpeta ñ')
        self.assertTrue((self.outside / 'secret').exists())

    def test_invalid_and_incomplete_paths(self):
        for name in ['../private/secret', '/etc/passwd', '.', '', '.incomplete/a', 'x//y', 'a.crdownload', 'a.part']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                drop.file_parent(name)

    def test_hidden_incomplete_and_links_not_listed(self):
        for name in ['.incomplete', 'a.part', 'b.crdownload', 'visible.txt']:
            (drop.FILES_DIR / name).write_text('ok')
        (drop.FILES_DIR / 'link').symlink_to(self.outside / 'secret')
        self.assertEqual([x['name'] for x in drop.listing('')], ['visible.txt'])

if __name__ == '__main__':
    unittest.main()
