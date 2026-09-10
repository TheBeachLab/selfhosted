#!/usr/bin/env python3
"""Conservative beets proposals; writes go through Nextcloud, never raw renames.

Pinned API: beets 2.14.0. https://docs.beets.io/en/latest/guides/tagger.html
MusicBrainz/AcoustID supply evidence. No generated artist or recording claims.
"""
import argparse
import collections
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import unicodedata

BASE = Path(os.environ.get('MUSIC_INBOX_STATE', '/var/lib/music-inbox'))
ROOT = Path('/var/www/nextcloud/data/admin/files')
BRIDGE = '/opt/music-inbox/bridge.php'
POLICY_VERSION = 5
MB_UNAVAILABLE = False
EXTENSIONS = {'.mp3', '.m4a', '.flac', '.wav', '.aif', '.aiff', '.ogg', '.opus', '.aac', '.wma', '.ape'}
FIELDS = ('title','artist','artists','album','albumartist','albumartists','track','tracktotal','disc','disctotal','year','month','day','genre','composer','comments','mb_trackid','mb_albumid','mb_artistid','mb_albumartistid','mb_releasetrackid','mb_releasegroupid','comp')

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def save(path, obj):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    temp.replace(path)

def bridge(op, **kwargs):
    result=subprocess.run(['php',BRIDGE], input=json.dumps(dict(op=op,**kwargs)),text=True,capture_output=True,timeout=180)
    if result.returncode: raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:])
    try:return json.loads(result.stdout)
    except json.JSONDecodeError as error:raise RuntimeError('Invalid Nextcloud bridge response: '+result.stderr[-1000:]) from error

def safe(value):
    value=unicodedata.normalize('NFC',str(value))
    value=re.sub(r'[/\\\x00-\x1f:*?"<>|]','_',value)
    value=re.sub(r'\.{2,}','.',value).strip(' .')
    return value[:150] or 'Unknown'

def destination(tags, suffix):
    artist=tags.get('albumartist') or tags.get('artist') or 'Unknown Artist'
    album=tags.get('album') or 'Singles'
    prefix=''
    if tags.get('track'):
        prefix=(f"{int(tags.get('disc') or 1):02d}-" if int(tags.get('disctotal') or 1)>1 else '')+f"{int(tags['track']):02d} - "
    return '/'.join([safe(artist),safe(album),safe(prefix+tags['title'])+suffix.lower()])

def special_version(text):
    return bool(re.search(r'\b(?:IA|AI cover|AI generated|instrumental|no.vocals|karaoke|remake|mashup)\b',text,re.I))

def version_markers(text):
    return set(re.findall(r'\b(?:live|remix|remaster(?:ed)?|edit|acoustic|demo)\b',text.casefold()))

def confidence(rec, distance, gap, durations, special=False):
    return rec=='strong' and distance<=0.05 and gap>=0.02 and all(d<=3 for d in durations) and not special

def read_item(path):
    from beets.library import Item
    item=Item.from_path(str(path))
    if not item.artist or not item.album or not item.title:
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format_tags','-of','json',str(path)],capture_output=True,text=True,timeout=20)
        tags={k.casefold():v for k,v in json.loads(probe.stdout or '{}').get('format',{}).get('tags',{}).items()}
        for field,aliases in {'artist':['artist'],'title':['title'],'album':['album'],'albumartist':['album_artist','album artist','albumartist'],'genre':['genre'],'composer':['composer'],'comments':['comment','comments']}.items():
            if not item.get(field):
                for alias in aliases:
                    if tags.get(alias):item[field]=tags[alias];break
        for field,alias in [('track','track'),('disc','disc'),('tracktotal','tracktotal'),('disctotal','disctotal'),('year','date')]:
            if not item.get(field) and tags.get(alias):
                m=re.match(r'\d+',tags[alias])
                if m:item[field]=int(m.group())
    if item.album:item.album=re.sub(r'\s+CD\s*\d+$','',item.album,flags=re.I)
    if not item.title:
        item.title=re.sub(r' \[[a-f0-9]{10}\]$','',Path(path).stem)
        item.title=re.sub(r'^\d{1,2}\.\s+','',item.title)
    return item

def setup_beets():
    from beets import config, plugins
    config['plugins']=['musicbrainz','chroma']
    config['musicbrainz']['search_limit']=3
    config['import']['from_scratch']=False
    plugins.load_plugins()
    from urllib3.util.retry import Retry
    for plugin in plugins.find_plugins():
        if plugin.name!='musicbrainz':continue
        # beets 2.14 defaults to six HTTP retries. The scheduler supplies retries;
        # one unavailable provider must not stall the entire inbox repeatedly.
        session=plugin.mb_api.session
        for adapter in session.adapters.values():adapter.max_retries=Retry(total=0)
        def availability(response,**kwargs):
            global MB_UNAVAILABLE
            if response.status_code>=500 or response.status_code==429:MB_UNAVAILABLE=True
            return response
        session.hooks['response'].append(availability)

def propose(records):
    from beets.library import Item
    from beets.autotag import Source,tag_album,tag_item
    from beetsplug import chroma
    from beets import logging
    items=[read_item(ROOT/r['path'].lstrip('/')) for r in records]
    # Strip import-specific filename suffix only when no usable embedded title exists.
    for item in items:
        if not item.title: item.title=re.sub(r' \[[a-f0-9]{10}\]$','',Path(os.fsdecode(item.path)).stem)
    album=len(items)>1 and all(i.album for i in items) and len({i.album for i in items})==1
    if not album and len(items)>1: raise ValueError('Mixed singleton group')
    source=Source.from_items(items) if album else Source.from_item(items[0])
    proposal=tag_album(source) if album else tag_item(source)
    # Fingerprinting supplements uncertain text matches; it is not treated as proof of an edition.
    if proposal.recommendation.name!='strong' and not MB_UNAVAILABLE:
        for item in items: chroma.acoustid_match(logging.getLogger('music-inbox'),item.path)
        proposal=tag_album(source) if album else tag_item(source)
    result={'time':time.time(),'sources':records,'recommendation':proposal.recommendation.name,'original_artist':source.artist,'original_album_or_title':source.name,'accepted':False,'candidates':[]}
    for match in proposal.candidates[:3]:
        info=match.info
        result['candidates'].append({'distance':float(match.distance),'artist':info.get('artist'),'title':info.get('album') or info.get('title'),'id':info.get('album_id') or info.get('track_id'),'url':info.get('data_url'),'source':info.get('data_source')})
    if not proposal.candidates: return result
    best=proposal.candidates[0]
    mapping=best.mapping if album else {items[0]:best.info}
    durations=[abs(i.length-info.length) for i,info in mapping.items() if info.length is not None]
    complete=len(mapping)==len(items) and len(durations)==len(items)
    distance=float(best.distance)
    gap=float(proposal.candidates[1].distance)-distance if len(proposal.candidates)>1 else 1
    version_mismatch=any(version_markers(i.title)!=version_markers(info.get('title') or '') for i,info in mapping.items())
    result['version_mismatch']=version_mismatch
    result['accepted']=complete and not version_mismatch and confidence(proposal.recommendation.name,distance,gap,durations,any(special_version(i.title) for i in items))
    result['max_duration_difference']=max(durations,default=None)
    result['gap']=gap
    best.apply_metadata(from_scratch=False)
    result['tracks']=[]
    for record,item in zip(records,items):
        tags={k:item.get(k) for k in FIELDS if item.get(k) is not None}
        result['tracks'].append({'source':record,'tags':tags,'destination':destination(tags,Path(record['path']).suffix)})
    return result

def scan():
    setup_beets()
    import requests
    try:
        health=requests.get('https://musicbrainz.org/ws/2/recording',params={'query':'artist:(aphex twin) recording:(qkthr)','fmt':'json','limit':1},timeout=8)
        musicbrainz_available=health.status_code==200
    except requests.RequestException: musicbrainz_available=False
    print('MusicBrainz available:',musicbrainz_available,flush=True)
    records=bridge('list')
    decisions=json.loads((BASE/'review.json').read_text()) if (BASE/'review.json').exists() else {}
    ready=set()
    for file in (BASE/'proposals').glob('*.json'):
        p=json.loads(file.read_text());decision=decisions.get(file.stem,{})
        if ((p.get('accepted') and p.get('policy_version')==POLICY_VERSION) or decision.get('approve')) and not decision.get('reject'):
            ready.update((t['source']['id'],t['source']['sha256']) for t in p.get('tracks',[]))
    groups=collections.defaultdict(list)
    from beets.library import Item
    for r in records:
        p=ROOT/r['path'].lstrip('/')
        if p.suffix.lower() not in EXTENSIONS or p.is_symlink(): continue
        if time.time()-max(r['mtime'],p.stat().st_mtime)<120: continue
        before=p.stat()
        r['sha256']=sha(p)
        after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): continue
        if (r['id'],r['sha256']) in ready:continue
        try:
            if r['size']==0: raise ValueError('Empty file')
            item=read_item(p)
            group=re.sub(r'\s+CD\s*\d+$','',str(p.parent),flags=re.I) if item.album and p.parent.name!='Singles' else str(p)
            groups[group].append(r)
        except Exception as e:
            save(BASE/'proposals'/f"{r['id']}.json",{'sources':[r],'accepted':False,'time':time.time(),'error':str(e)})
    for key,group in sorted(groups.items()):
        token=hashlib.sha256('\n'.join(f"{r['id']}:{r['sha256']}" for r in sorted(group,key=lambda x:x['id'])).encode()).hexdigest()[:20]
        file=BASE/'proposals'/f'{token}.json'
        if file.exists():
            previous=json.loads(file.read_text())
            retry_after=3600 if previous.get('error') else 7*86400
            if previous.get('policy_version')==POLICY_VERSION and time.time()-file.stat().st_mtime<retry_after: continue
        print('Recognizing',key,flush=True)
        try:
            def timeout(signum,frame): raise TimeoutError('Recognition timed out; will retry')
            signal.signal(signal.SIGALRM,timeout)
            signal.alarm(min(1200,180+len(group)*5))
            import apple
            result=apple.propose(group,BASE,ROOT,destination,special_version,version_markers,FIELDS,read_item)
            # For loose tracks with poor/no tags, recognize the audio without depending on MB search uptime.
            if not result.get('tracks') and len(group)==1:
                import acoustic
                fingerprint=acoustic.propose(group[0],BASE,ROOT,read_item,FIELDS,destination,special_version,version_markers)
                if fingerprint.get('tracks'):result=fingerprint
            if not result.get('tracks') and musicbrainz_available and not MB_UNAVAILABLE:
                fallback=propose(group)
                if fallback.get('tracks'): result=fallback
            if not result.get('tracks') and (not musicbrainz_available or MB_UNAVAILABLE):
                result['error']='MusicBrainz temporarily unavailable; retry later'
        except Exception as e: result={'sources':group,'accepted':False,'time':time.time(),'error':str(e)}
        finally: signal.alarm(0)
        result['policy_version']=POLICY_VERSION
        save(file,result)
        # Keep independently reviewable recording evidence for unmatched album tracks.
        # A partial catalog match must not prevent fingerprinting the rest of an album.
        if len(group)>1:
            mapped={t['source']['id'] for t in result.get('tracks',[])}
            import acoustic
            for record in group:
                if record['id'] in mapped:continue
                fingerprint_file=BASE/'proposals'/f"acoustic-{record['id']}-{record['sha256'][:20]}.json"
                if fingerprint_file.exists():
                    previous=json.loads(fingerprint_file.read_text())
                    if time.time()-fingerprint_file.stat().st_mtime<(3600 if previous.get('error') else 7*86400):continue
                try:
                    signal.alarm(120)
                    fingerprint=acoustic.propose(record,BASE,ROOT,read_item,FIELDS,destination,special_version,version_markers)
                except Exception as e:fingerprint={'sources':[record],'accepted':False,'time':time.time(),'error':str(e)}
                finally:signal.alarm(0)
                fingerprint['policy_version']=POLICY_VERSION
                save(fingerprint_file,fingerprint)

def audio_hash(path):
    r=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-'],capture_output=True,text=True,timeout=180)
    if r.returncode: raise RuntimeError('Cannot validate audio stream: '+r.stderr[-500:])
    return r.stdout.strip()

def artwork(stage,tags,cover_url=None):
    # Retain existing artwork; download only a missing front cover from the matched release.
    from mediafile import MediaFile,Image,ImageType
    import requests
    media=MediaFile(str(stage))
    if media.images: return
    url='https://coverartarchive.org/release/'+tags['mb_albumid']+'/front-500' if tags.get('mb_albumid') else cover_url
    if not url: return
    cache=BASE/'covers';cache.mkdir(exist_ok=True)
    file=cache/hashlib.sha256(url.encode()).hexdigest()
    if file.exists():content=file.read_bytes()
    else:
        response=requests.get(url,timeout=20,stream=True)
        if response.status_code!=200:return
        content=b''
        for block in response.iter_content(65536):
            content+=block
            if len(content)>5*1024*1024:return
    import io
    from PIL import Image as PILImage
    with PILImage.open(io.BytesIO(content)) as img: img.verify()
    if not file.exists():file.write_bytes(content)
    media.images=[Image(content,type=ImageType.front)];media.save()

def apply():
    from beets.library import Item
    decisions=json.loads((BASE/'review.json').read_text()) if (BASE/'review.json').exists() else {}
    for file in sorted((BASE/'proposals').glob('*.json')):
        proposal=json.loads(file.read_text())
        if not proposal.get('accepted') and not decisions.get(file.stem,{}).get('approve'): continue
        if decisions.get(file.stem,{}).get('reject'): continue
        for track in proposal.get('tracks',[]):
            r=track['source'];p=ROOT/r['path'].lstrip('/')
            done=BASE/'done'/f"{r['id']}.json"
            if done.exists(): continue
            if not p.exists() or sha(p)!=r['sha256']: continue
            try:
                backup=BASE/'originals'/(r['sha256']+p.suffix)
                if not backup.exists(): shutil.copy2(p,backup)
                if sha(backup)!=r['sha256']: raise RuntimeError('Backup mismatch')
                stage=BASE/'stage'/(str(r['id'])+p.suffix)
                shutil.copy2(p,stage)
                item=Item.from_path(str(stage));item.update(track['tags']);item.write()
                try: artwork(stage,track['tags'],track.get('cover_url'))
                except Exception as e: print('Cover unavailable:',str(e),flush=True)
                if audio_hash(p)!=audio_hash(stage): raise RuntimeError('Audio stream changed')
                result=bridge('apply',id=r['id'],sha256=r['sha256'],stage=str(stage),staged_sha256=sha(stage),destination=track['destination'])
                save(done,dict(source=r,result=result,proposal=file.name,time=time.time(),review=decisions.get(file.stem)))
                (BASE/'errors'/f"{r['id']}.json").unlink(missing_ok=True)
                stage.unlink()
                print('Organized',result['path'],flush=True)
            except Exception as e:
                save(BASE/'errors'/f"{r['id']}.json",{'source':r,'error':str(e),'time':time.time()})
                print('Pending:',str(e),flush=True)

def report():
    live={r['id']:r for r in bridge('list') if Path(r['path']).suffix.lower() in EXTENSIONS}
    done=list((BASE/'done').glob('*.json'))
    preserved=sum(bool((json.loads(p.read_text()).get('review') or {}).get('identity_only')) for p in done)
    failures={int(p.stem):json.loads(p.read_text()) for p in (BASE/'errors').glob('*.json')}
    lines=['# Importación de música','',f'Actualizado: {time.strftime("%Y-%m-%d %H:%M:%S %Z")}', '',f'Organizadas: {len(done)}. Pendientes en imported: {len(live)}.', '', 'Añade canciones o carpetas de álbumes a `Music/imported`. Se revisan automáticamente cada cinco minutos. Las coincidencias dudosas permanecen aquí para revisión. Los originales de los archivos modificados se conservan en el servidor.', '', '## Pendientes','']
    if preserved:lines[5:5]=[f'{preserved} pistas se organizaron conservando las etiquetas originales tras contrastar su identidad con huellas acústicas. La edición concreta no se verificó de forma independiente.','']
    for r in sorted(live.values(),key=lambda r:r['path']):
        reason='coincidencia insuficiente; revisión pendiente'
        if not r['size']:reason='archivo vacío'
        elif special_version(r['path']):reason='versión especial; identificación manual'
        if r['id'] in failures:
            error=failures[r['id']]['error']
            reason='ya existe el destino; original conservado para revisar duplicados' if 'Destination exists' in error else 'error al procesar; original conservado'
        lines.append('- '+r['path'].replace('\n',' ')+' — '+reason)
    bridge('report',text='\n'.join(lines)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['scan','apply','run','report']);args=parser.parse_args()
    for d in ['proposals','originals','stage','done','errors']: (BASE/d).mkdir(parents=True,exist_ok=True)
    with (BASE/'lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        try:
            if args.mode in ('scan','run'): scan()
            if args.mode in ('apply','run'):
                apply()
                subprocess.run(['php','/var/www/nextcloud/occ','music:scan','admin','--folder=Music'],check=True,timeout=600,stdout=subprocess.DEVNULL)
        finally:report()

if __name__=='__main__': main()
