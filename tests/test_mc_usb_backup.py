"""Exercise the real shell workflow with temporary storage and fake host commands."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'services/mc-usb-backup'

@unittest.skipUnless(sys.platform.startswith('linux'), 'GNU userland workflow; run on Linux')
class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.usb = self.root / 'usb'
        self.files = self.usb / 'minecraft'
        self.files.mkdir(parents=True)
        self.world = self.root / 'world'
        self.world.mkdir()
        self.props = self.root / 'server.properties'
        self.props.write_text('rcon.port=25575\nrcon.password=fixture\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'commands'
        fake = '''#!/usr/bin/python3
import os,sys,pathlib,shutil
name=pathlib.Path(sys.argv[0]).name
with open(os.environ['LOG'],'a') as f:f.write(name+' '+ ' '.join(sys.argv[1:])+'\\n')
if name=='systemctl': print(os.environ.get('SERVER_STATE','inactive'))
elif name=='findmnt': print('/dev/fake' if sys.argv[-1]=='SOURCE' else 'exfat')
elif name=='blkid': print(os.environ.get('USB_ID','FEF9-F572'))
elif name=='du': print('10 fixture')
elif name=='df': print('Avail\\n99999999999')
elif name=='mcrcon' and os.environ.get('RCON_FAIL')==sys.argv[-1]: sys.exit(1)
elif name=='tar':
 if '-cf' in sys.argv: pathlib.Path(sys.argv[sys.argv.index('-cf')+1]).write_bytes(b'world archive')
 elif os.environ.get('BAD_ARCHIVE'): sys.exit(1)
elif name=='cp':
 shutil.copyfile(sys.argv[-2],sys.argv[-1])
 if os.environ.get('BAD_COPY'): pathlib.Path(sys.argv[-1]).write_bytes(b'corrupt')
'''
        for name in ['systemctl','findmnt','mountpoint','blkid','du','df','mcrcon','tar','zstd','cp']:
            p = self.bin / name
            p.write_text(fake)
            p.chmod(0o755)
        source = SOURCE.read_text()
        replacements = dict(WORLD_DIR=self.world, SERVER_PROPERTIES=self.props,
            MCRCON=self.bin/'mcrcon', LOCAL_DIR=self.root/'local', USB_MOUNT=self.usb,
            STATE_DIR=self.root/'state', LOCK_FILE=self.root/'backup.lock')
        for key, value in replacements.items():
            source = re.sub(rf'^readonly {key}=.*$', f'readonly {key}="{value}"', source, flags=re.M)
        self.script = self.root / 'backup'
        self.script.write_text(source)
        for date in ['2026-10-04','2026-10-14']:
            name = f'world-{date}_024629Z.tar.zst'
            (self.files/name).write_bytes(b'old archive')
            (self.files/(name+'.sha256')).write_text('old hash')
        (self.files/'pre26.3-world.tar.zst').write_bytes(b'historical')
    def run_backup(self, **extra):
        env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'], LOG=str(self.log), **extra)
        return subprocess.run(['bash',str(self.script),'--manual'],env=env,text=True,capture_output=True)
    def archives(self):
        return sorted(p.name for p in self.files.glob('world-*.tar.zst'))
    def test_offline_backup_retains_two_and_preserves_historical(self):
        result = self.run_backup()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.archives()),2)
        self.assertEqual((self.root/'state/manual-last-success').read_text().strip(),self.archives()[-1])
        self.assertTrue(self.archives()[0].startswith('world-2026-10-14'))
        self.assertTrue((self.files/'pre26.3-world.tar.zst').exists())
        self.assertNotIn('mcrcon ',self.log.read_text())
        self.assertNotIn('systemctl start',self.log.read_text())
    def test_wrong_usb_preserves_copies(self):
        before=self.archives()
        self.assertNotEqual(self.run_backup(USB_ID='WRONG').returncode,0)
        self.assertEqual(self.archives(),before)
        self.assertNotIn('tar ',self.log.read_text())
    def test_failed_copy_or_archive_never_rotates(self):
        for flag in ['BAD_COPY','BAD_ARCHIVE']:
            with self.subTest(flag=flag):
                before=self.archives()
                self.assertNotEqual(self.run_backup(**{flag:'1'}).returncode,0)
                self.assertEqual(self.archives(),before)
                self.assertFalse(list(self.files.glob('*.partial')))
    def test_live_flush_failure_reenables_saving(self):
        result=self.run_backup(SERVER_STATE='active',RCON_FAIL='save-all flush')
        self.assertNotEqual(result.returncode,0)
        log=self.log.read_text()
        self.assertIn('save-off',log);self.assertIn('save-on',log)
        self.assertEqual(len(self.archives()),2)
    def test_transition_rejected(self):
        self.assertNotEqual(self.run_backup(SERVER_STATE='deactivating').returncode,0)
        self.assertEqual(len(self.archives()),2)

if __name__=='__main__':unittest.main()
