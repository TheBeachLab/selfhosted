import importlib.util
from pathlib import Path
import unittest
import tempfile
import subprocess
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('organize',Path(__file__).with_name('organize.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PolicyTests(unittest.TestCase):
    def test_musicbrainz_outage_disables_repeated_fallbacks(self):
        from beets import plugins
        from requests import Response
        module.MB_UNAVAILABLE=False
        module.setup_beets()
        plugin=next(p for p in plugins.find_plugins() if p.name=='musicbrainz')
        self.assertTrue(all(a.max_retries.total==0 for a in plugin.mb_api.session.adapters.values()))
        response=Response();response.status_code=503
        for hook in plugin.mb_api.session.hooks['response']:hook(response)
        self.assertTrue(module.MB_UNAVAILABLE)
        module.MB_UNAVAILABLE=False

    def test_fingerprint_credits_and_ambiguous_recordings(self):
        import acoustic,json
        class Item(dict):
            def __getattr__(self,k):return self.get(k)
        item=Item(title='Song',artist='',album='',length=120)
        recording=dict(id='recording-id',title='Song',duration=120,artists=[{'name':'One'},{'name':'Two'}])
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'fingerprints').mkdir()
            cache=base/'fingerprints'/'source.json'
            data={'results':[{'score':.999,'recordings':[recording]}]}
            cache.write_text(json.dumps(data))
            args=({'path':'/in/song.mp3','sha256':'source'},base,base,lambda p:item,module.FIELDS,module.destination,module.special_version,module.version_markers)
            result=acoustic.propose(*args)
            self.assertTrue(result['accepted'])
            self.assertEqual(result['tracks'][0]['tags']['artist'],'One & Two')
            data['results'][0]['recordings'].append(dict(recording,title='Different song'))
            cache.write_text(json.dumps(data))
            self.assertFalse(acoustic.propose(*args)['accepted'])

    def test_nonstandard_alac_tags_are_read_and_audio_is_preserved(self):
        try:
            from beets.library import Item
        except ImportError:self.skipTest('Run this integration check in the pinned server venv')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sample.m4a'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440','-t','0.3','-c:a','alac','-movflags','use_metadata_tags','-metadata','ARTIST=Example','-metadata','ALBUM=Record CD2','-metadata','TITLE=Song','-metadata','disc=2',str(p)],check=True)
            item=module.read_item(p)
            self.assertEqual((item.artist,item.album,item.title),('Example','Record','Song'))
            before=module.audio_hash(p)
            item.write()
            self.assertEqual(module.audio_hash(p),before)

    def test_unmatched_compilation_catalog_falls_back_without_changing_album(self):
        import apple
        class Item(dict):
            def __getattr__(self,k):return self.get(k)
        item=Item(artist='Correct Band',title='Song',album='Sampler',albumartist='Various Artists',comp=True,length=120,track=7,disc=1)
        calls=[]
        def request(base,endpoint,params):
            calls.append((endpoint,params))
            if endpoint=='lookup':return {'results':[dict(kind='song',artistName='Wrong Band',trackName='Other',trackTimeMillis=120000,collectionName='Sampler')]}
            if params['entity']=='album':return {'results':[dict(collectionName='Sampler',artistName='Various Artists',collectionId=1)]}
            return {'results':[dict(kind='song',artistName='Correct Band',trackName='Song',trackTimeMillis=120000,collectionName='Original Album',trackNumber=2)]}
        with patch.object(apple,'request',request):
            result=apple.propose([{'path':'/in/song.mp3'}],Path('/tmp'),Path('/tmp'),module.destination,module.special_version,module.version_markers,module.FIELDS,lambda p:item)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['tracks'][0]['tags']['album'],'Sampler')
        self.assertEqual(result['tracks'][0]['tags']['track'],7)
        self.assertEqual(len(calls),3)
    def test_catalog_comparison_does_not_equate_empty_or_foreign_names(self):
        import apple
        self.assertEqual(apple.similarity('', ''),0)
        self.assertLess(apple.similarity('東京','大阪'),.94)
        self.assertEqual(apple.similarity('Felicità','Felicita'),1)
    def test_uncertain_and_close_competitors_stay_pending(self):
        self.assertFalse(module.confidence('medium',0.01,0.2,[0]))
        self.assertFalse(module.confidence('strong',0.01,0.001,[0]))
        self.assertFalse(module.confidence('strong',0.01,0.2,[12]))
        self.assertFalse(module.confidence('strong',0.01,0.2,[0],True))
        self.assertTrue(module.confidence('strong',0.01,0.2,[0.2,0.8]))

    def test_destination_cannot_escape_and_normalizes_unicode(self):
        value=module.destination({'artist':'../../evil','album':'a/b','title':'Pe\u0301rche\u0301','track':2},'.FLAC')
        self.assertNotIn('..',value)
        self.assertEqual(len(value.split('/')),3)
        self.assertTrue(value.endswith('02 - Pérché.flac'))

    def test_multidisc_track_names_cannot_collide(self):
        tags={'artist':'A','album':'B','title':'C','track':1,'disctotal':2}
        self.assertNotEqual(module.destination(dict(tags,disc=1),'.mp3'),module.destination(dict(tags,disc=2),'.mp3'))

    def test_ai_and_stems_are_not_official_recordings(self):
        self.assertTrue(module.special_version('La Falda - Bad Bunny (Visualizer Oficial) IA'))
        self.assertTrue(module.special_version('Song no_vocals'))
        self.assertFalse(module.special_version('Mountains'))

if __name__=='__main__': unittest.main()
