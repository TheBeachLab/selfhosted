"""AcoustID recording evidence through beets' bundled public lookup client.
https://acoustid.org/webservice (lookup only; no fingerprint submissions).
"""
import json,time
from pathlib import Path
import acoustid
from beetsplug.chroma import API_KEY
from apple import norm,similarity,clean_hint

def propose(record,base,root,read_item,fields,destination,special_version,version_markers):
    path=root/record['path'].lstrip('/');item=read_item(path)
    result={'sources':[record],'tracks':[],'accepted':False,'provider':'AcoustID / MusicBrainz recording data','time':time.time()}
    if special_version(item.title):return result
    cache=base/'fingerprints';cache.mkdir(exist_ok=True);file=cache/(record['sha256']+'.json')
    if file.exists():data=json.loads(file.read_text())
    else:
        duration,fp=acoustid.fingerprint_file(str(path))
        data=acoustid.lookup(API_KEY,fp,duration,meta='recordings',timeout=10)
        file.write_text(json.dumps(data));time.sleep(1)
    results=sorted(data.get('results',[]),key=lambda r:r['score'],reverse=True)
    if not results:return result
    best=results[0];choices=[]
    for recording in best.get('recordings',[]):
        if not recording.get('title') or not recording.get('artists') or not recording.get('duration'):continue
        artist=''.join(a['name']+a.get('joinphrase',' & ' if n<len(recording['artists'])-1 else '') for n,a in enumerate(recording['artists']))
        duration=abs(item.length-recording['duration'])
        choices.append((recording,artist,duration))
    if not choices:return result
    choices.sort(key=lambda c:c[2]);recording,artist,diff=choices[0]
    identities={(norm(c[0]['title']),norm(c[1])) for c in choices}
    artist_hint=item.artist;title_hint=clean_hint(item.title)
    if not artist_hint and ' - ' in title_hint:artist_hint,title_hint=title_hint.split(' - ',1)
    agreement=similarity(artist_hint,artist)>=.94 and similarity(title_hint,recording['title'])>=.94
    gap=best['score']-results[1]['score'] if len(results)>1 else 1
    accepted=len(identities)==1 and diff<=3 and gap>=.05 and (best['score']>=.98 or best['score']>=.95 and agreement)
    accepted=accepted and version_markers(item.title)==version_markers(recording['title'])
    tags={k:item.get(k) for k in fields if item.get(k) is not None}
    tags.update(title=recording['title'],artist=artist,artists=[a['name'] for a in recording['artists']],mb_trackid=recording['id'])
    if not tags.get('album'):tags.update(album='Singles',albumartist=artist,track=0,disc=0,tracktotal=0,disctotal=0)
    result.update(accepted=accepted,recommendation='fingerprint match',score=best['score'],gap=gap,identity_count=len(identities),max_duration_difference=diff,hint_agreement=agreement,evidence=[{'url':'https://musicbrainz.org/recording/'+recording['id'],'title':recording['title'],'artist':artist,'duration_difference':diff}],tracks=[{'source':record,'tags':tags,'destination':destination(tags,path.suffix)}])
    return result
