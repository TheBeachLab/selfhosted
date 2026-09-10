import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('mac_drop',Path(__file__).with_name('mac-drop.py'))
drop=importlib.util.module_from_spec(spec);spec.loader.exec_module(drop)

class TransferTests(unittest.TestCase):
    def test_only_verified_receipt_removes_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'song.mp3';p.write_bytes(b'original audio')
            def transport(path,meta):return dict(meta,file_id=123,path='/Music/imported/song.mp3')
            drop.transfer(p,root,root,transport)
            self.assertFalse(p.exists())
            self.assertEqual(json.loads((root/'transfers.jsonl').read_text())['server']['file_id'],123)

    def test_failure_or_mismatched_receipt_preserves_source(self):
        for mode in ['network','hash']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);p=root/'song.mp3';p.write_bytes(b'original audio')
                def transport(path,meta):
                    if mode=='network':raise RuntimeError('offline')
                    return dict(meta,sha256='wrong',file_id=123)
                with self.assertRaises(RuntimeError):drop.transfer(p,root,root,transport)
                self.assertEqual(p.read_bytes(),b'original audio')

    def test_source_edited_during_upload_is_retained(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'song.mp3';p.write_bytes(b'original audio')
            def transport(path,meta):
                path.write_bytes(b'changed audio');return dict(meta,file_id=123)
            with self.assertRaises(RuntimeError):drop.transfer(p,root,root,transport)
            self.assertEqual(p.read_bytes(),b'changed audio')

if __name__=='__main__':unittest.main()
