import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location('podcast_build', Path(__file__).with_name('build.py'))
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class PublicationBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.content = self.root / 'content'
        (self.content / 'episodes').mkdir(parents=True)
        self.media = self.root / 'media'
        self.media.mkdir()
        self.show = json.loads(Path(__file__).with_name('content').joinpath('show.json').read_text())
        self.episode = json.loads(Path(__file__).with_name('content').joinpath('episodes/001.json').read_text())

    def run_build(self):
        (self.content / 'show.json').write_text(json.dumps(self.show))
        (self.content / 'episodes/001.json').write_text(json.dumps(self.episode))
        return BUILD.build(self.content, self.media, self.root / 'public')

    def test_draft_script_and_unreferenced_media_never_published(self):
        self.episode['description'] = 'PRIVATE-DRAFT-TEXT'
        (self.media / 'private.mp3').write_bytes(b'private')
        self.assertEqual(self.run_build(), 0)
        output = self.root / 'public'
        self.assertEqual(ET.parse(output / 'feed.xml').findall('./channel/item'), [])
        self.assertNotIn('PRIVATE-DRAFT-TEXT', (output / 'index.html').read_text())
        self.assertEqual(list((output / 'media').iterdir()), [])

    def test_unfinalized_show_blocks_publication(self):
        self.episode['status'] = 'published'
        with self.assertRaisesRegex(ValueError, 'Finalize'):
            self.run_build()

    def test_real_audio_publishes_with_correct_enclosure(self):
        self.show['provisional_title'] = False
        self.show['cover'] = 'cover.jpg'
        self.episode.update(status='published', audio='001.mp3', published_at='2026-01-01T12:00:00+00:00')
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=white:s=1400x1400',
                        '-frames:v', '1', str(self.media / 'cover.jpg')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
                        '-t', '1', str(self.media / '001.mp3')], check=True)
        self.assertEqual(self.run_build(), 1)
        enclosure = ET.parse(self.root / 'public/feed.xml').find('./channel/item/enclosure')
        self.assertEqual(enclosure.attrib['type'], 'audio/mpeg')
        self.assertEqual(int(enclosure.attrib['length']), (self.media / '001.mp3').stat().st_size)
        self.assertEqual(enclosure.attrib['url'], self.show['base_url'] + 'media/001.mp3')

    def test_existing_release_cannot_be_overwritten(self):
        (self.root / 'public').mkdir()
        with self.assertRaises(FileExistsError):
            self.run_build()

    def test_directory_traversal_in_cover_rejected(self):
        self.show['cover'] = '../private.png'
        with self.assertRaisesRegex(ValueError, 'ASCII'):
            self.run_build()


if __name__ == '__main__':
    unittest.main()
