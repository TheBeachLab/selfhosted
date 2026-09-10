"""Apple catalog fallback, with cached requests below its documented 20/min limit.
https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html
Only strict title/artist/duration matches can be accepted. No invented metadata.
"""
import hashlib,json,re,time,unicodedata
from pathlib import Path
from difflib import SequenceMatcher
import requests

last_request=0.0
def request(base, endpoint, params):
    global last_request
    cache=base/'catalog-cache';cache.mkdir(exist_ok=True)
    key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
    file=cache/(key+'.json')
    if file.exists() and time.time()-file.stat().st_mtime<7*86400:return json.loads(file.read_text())
    time.sleep(max(0,3.2-(time.monotonic()-last_request)))
    last_request=time.monotonic()
    response=requests.get('https://itunes.apple.com/'+endpoint,params=params,timeout=15)
    response.raise_for_status();data=response.json();file.write_text(json.dumps(data))
    return data

def norm(text):
    text=unicodedata.normalize('NFKD',text).casefold()
    return ''.join(c for c in text if c.isalnum())

def similarity(a,b):
    a,b=norm(a),norm(b)
    return SequenceMatcher(None,a,b).ratio() if a and b else 0.0

def clean_hint(text):
    text=re.sub(r'\s*\[(?:[A-Za-z0-9_-]{10,12})\]','',text)
    text=re.sub(r'\s*[\[(](?:official (?:music )?(?:video|audio|lyric video)|lyrics?|hq|hd|4k remaster)[\])]','',text,flags=re.I)
    return text.strip()

def propose(records,base,root,destination,special_version,version_markers,fields,read_item):
    items=[read_item(root/r['path'].lstrip('/')) for r in records]
    result={'time':time.time(),'sources':records,'accepted':False,'recommendation':'none','provider':'Apple iTunes','candidates':[],'tracks':[]}
    if any(special_version(i.title) for i in items):
        result['error']='Special/AI/stem version requires manual identification';return result
    album=items[0].album if all(i.album==items[0].album for i in items) else ''
    albumartist=items[0].albumartist or items[0].artist
    catalog=[]
    if album:
        albums=request(base,'search',{'term':albumartist+' '+album,'entity':'album','country':'US','limit':5})['results']
        for entry in albums:
            if similarity(entry.get('collectionName',''),album)<.68:continue
            if albumartist and not items[0].comp and similarity(entry.get('artistName',''),albumartist)<.8:continue
            songs=[r for r in request(base,'lookup',{'id':entry['collectionId'],'entity':'song','limit':200,'country':'US'})['results'] if r.get('kind')=='song']
            catalog.extend(songs)
    evidence=[];pending=[]
    for item,record in zip(items,records):
        artist=item.artist;title=clean_hint(item.title)
        if not artist and ' - ' in title:artist,title=title.split(' - ',1)
        if not artist:
            pending.append(item.title+': no reliable artist hint');continue
        choices=catalog
        if not choices:
            choices=request(base,'search',{'term':artist+' '+title,'entity':'song','country':'US','limit':10})['results']
        def rank(options):
            ranked=[]
            for candidate in options:
                if candidate.get('kind')!='song':continue
                ts=similarity(title,candidate['trackName']);ars=similarity(artist,candidate['artistName'])
                duration=abs(item.length-candidate.get('trackTimeMillis',0)/1000)
                if ts<.94 or ars<.94 or duration>3:continue
                if version_markers(item.title)!=version_markers(candidate['trackName']):continue
                ranked.append((ts+ars,candidate,duration))
            return ranked
        ranked=rank(choices)
        if not ranked and catalog:
            ranked=rank(request(base,'search',{'term':artist+' '+title,'entity':'song','country':'US','limit':10})['results'])
        ranked.sort(key=lambda x:x[0],reverse=True)
        if not ranked:
            pending.append(item.title+': no strict artist/title/duration match');continue
        chosen=ranked[0][1]
        # Equivalent reissues are fine for recording labels, but don't invent an album for loose songs.
        tags={k:item.get(k) for k in fields if item.get(k) is not None}
        tags.update(title=chosen['trackName'],artist=chosen['artistName'],artists=[chosen['artistName']])
        matched_album=bool(album and similarity(album,chosen['collectionName'])>=.9)
        if matched_album:
            tags.update(album=chosen['collectionName'],track=chosen.get('trackNumber',item.track),disc=chosen.get('discNumber',item.disc),tracktotal=chosen.get('trackCount',item.tracktotal),disctotal=chosen.get('discCount',item.disctotal))
        elif not album:
            tags.update(album='Singles',albumartist=chosen['artistName'],track=0,disc=0,tracktotal=0,disctotal=0)
        evidence.append({'url':chosen.get('trackViewUrl'),'artist':chosen['artistName'],'title':chosen['trackName'],'album':chosen['collectionName'],'duration_difference':ranked[0][2],'title_similarity':ranked[0][0]-similarity(artist,chosen['artistName']),'album_preserved':not matched_album})
        result['tracks'].append({'source':record,'tags':tags,'destination':destination(tags,Path(record['path']).suffix),'cover_url':chosen.get('artworkUrl100') if matched_album or not album else None})
    result.update(accepted=bool(evidence),recommendation='strict catalog match',evidence=evidence,pending=pending,max_duration_difference=max((e['duration_difference'] for e in evidence),default=None))
    return result
