#!/usr/bin/env python3
"""Build a static audio podcast. Draft content is never copied to the public tree."""
import argparse
from datetime import datetime
from email.utils import format_datetime
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ITUNES = 'http://www.itunes.com/dtds/podcast-1.0.dtd'
ATOM = 'http://www.w3.org/2005/Atom'
ET.register_namespace('itunes', ITUNES)
ET.register_namespace('atom', ATOM)


def build(content, media, output):
    show = json.loads((content / 'show.json').read_text())
    base = show['base_url']
    if not base.startswith('https://') or not base.endswith('/'):
        raise ValueError('base_url must be an absolute HTTPS URL ending in /')
    # Require a new directory; deploy switches a symlink only after successful validation.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'media').mkdir()
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    def tag(parent, name, value):
        ET.SubElement(parent, name).text = str(value)
    tag(channel, 'title', show['title'])
    tag(channel, 'link', base)
    tag(channel, 'description', show['description'])
    tag(channel, 'language', show['language'])
    tag(channel, f'{{{ITUNES}}}author', show['author'])
    tag(channel, f'{{{ITUNES}}}explicit', str(show['explicit']).lower())
    ET.SubElement(channel, f'{{{ATOM}}}link', href=base + 'feed.xml', rel='self', type='application/rss+xml')
    category = ET.SubElement(channel, f'{{{ITUNES}}}category', text=show['category'])
    if show.get('subcategory'):
        ET.SubElement(category, f'{{{ITUNES}}}category', text=show['subcategory'])

    def asset(name, extensions):
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*', name):
            raise ValueError('Media must have plain ASCII filenames without directories')
        source = media / name
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in extensions:
            raise ValueError(f'Invalid media: {name}')
        target = output / 'media' / name
        shutil.copyfile(source, target)
        return target, base + 'media/' + name

    if show.get('cover'):
        cover, cover_url = asset(show['cover'], {'.jpg', '.jpeg', '.png'})
        dimensions = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=width,height', '-of', 'json', str(cover)]))['streams'][0]
        if dimensions['width'] != dimensions['height'] or not 1400 <= dimensions['width'] <= 3000:
            raise ValueError('Cover must be square, 1400–3000 pixels')
        ET.SubElement(channel, f'{{{ITUNES}}}image', href=cover_url)

    cards, seen, urls = [], set(), set()
    episodes = [json.loads(p.read_text()) for p in sorted((content / 'episodes').glob('*.json'))]
    for episode in reversed(episodes):
        if episode['status'] == 'draft':
            continue
        if episode['status'] != 'published':
            raise ValueError('Unknown episode status')
        if show.get('provisional_title') or not show.get('cover'):
            raise ValueError('Finalize the show name and cover before publishing an episode')
        guid = episode['guid']
        if not guid or guid in seen:
            raise ValueError('Episode GUID must be unique and stable')
        seen.add(guid)
        date = datetime.fromisoformat(episode['published_at'])
        if date.tzinfo is None or date > datetime.now(date.tzinfo):
            raise ValueError('Publication requires a non-future timestamp with timezone')
        audio, audio_url = asset(episode['audio'], {'.mp3', '.m4a'})
        if audio_url in urls:
            raise ValueError('Audio enclosure URL must be unique')
        urls.add(audio_url)
        probe = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
            '-of', 'json', str(audio)]))
        if not any(s['codec_type'] == 'audio' for s in probe['streams']):
            raise ValueError('No audio stream found')
        duration = float(probe['format']['duration'])
        if not 0 < duration <= 300:
            raise ValueError('Episode must be longer than zero and at most five minutes')
        item = ET.SubElement(channel, 'item')
        tag(item, 'title', episode['title'])
        tag(item, 'description', episode['description'])
        ET.SubElement(item, 'guid', isPermaLink='false').text = guid
        tag(item, 'pubDate', format_datetime(date))
        tag(item, f'{{{ITUNES}}}duration', round(duration))
        tag(item, f'{{{ITUNES}}}episode', episode['number'])
        tag(item, f'{{{ITUNES}}}explicit', str(show['explicit']).lower())
        ET.SubElement(item, 'enclosure', url=audio_url, length=str(audio.stat().st_size),
                      type='audio/mpeg' if audio.suffix == '.mp3' else 'audio/mp4')
        extras = ''
        for key, extensions, label in [('video', {'.mp4'}, 'Video'), ('transcript', {'.txt', '.vtt'}, 'Transkript')]:
            if episode.get(key):
                _, url = asset(episode[key], extensions)
                extras += f'<p><a href="{escape(url, quote=True)}">{label}</a></p>'
        cards.append(f'<article><h2>{escape(episode["title"])}</h2><p>{escape(episode["description"])}</p>'
                     f'<audio controls preload="none" src="{escape(audio_url, quote=True)}"></audio>'
                     f'<p><a href="{escape(audio_url, quote=True)}">Audio herunterladen</a></p>{extras}</article>')
    ET.indent(root)
    ET.ElementTree(root).write(output / 'feed.xml', encoding='utf-8', xml_declaration=True)
    title = escape(show['title'])
    label = '<p>Arbeitstitel · Podcast in Vorbereitung</p>' if show.get('provisional_title') else ''
    body = ''.join(cards) or '<p>Die erste Folge ist in Vorbereitung.</p>'
    (output / 'index.html').write_text(f'''<!doctype html>
<html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{title} — Podcast</title>
<link rel="alternate" type="application/rss+xml" title="Podcast" href="feed.xml">
<style>body{{font:18px/1.6 system-ui,sans-serif;max-width:720px;margin:60px auto;padding:0 24px;color:#24352d;background:#faf9f5}}a{{color:#265b47}}audio{{width:100%}}article{{border-top:1px solid #ddd;padding:24px 0}}footer{{margin-top:60px;font-size:14px}}</style>
<main>{label}<h1>{title}</h1><p>{escape(show['description'])}</p>{body}
<p><a href="feed.xml">RSS-Feed</a></p></main>
<footer><a href="/">Arroyo</a> · <a href="/impressum.html">Impressum</a> · <a href="/datenschutz.html">Datenschutz</a></footer></html>''')
    return len(cards)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(f'Built {build(args.content, args.media, args.output)} published episodes; drafts excluded.')
