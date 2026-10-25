# Small-space housing podcast

A static audio podcast at https://arroyo.ing/podcast/ with its feed at
https://arroyo.ing/podcast/feed.xml. Working name: Micro Housing. No episodes
are published. The first German script is in drafts/001-de.md.

## Runtime

Nginx serves /var/www/podcast/current through an isolated /podcast/ location
in the existing arroyo.ing HTTPS virtual host. No database, daemon or new
listening port is needed. Access logs remain disabled by the parent host.
Current page/feed are intentionally noindex until launch.

- /home/git/podcast/content: private show metadata and episode manifests
- /home/git/podcast/drafts: private scripts
- /home/git/podcast/incoming: original recording uploads, private
- /home/git/podcast/media: approved audio/video/transcripts, private staging
- /home/git/podcast/exports: generated video and vertical clips, private
- /var/www/podcast/releases: immutable generated releases
- /var/www/podcast/current: symlink to the active release
- /usr/local/lib/housing-podcast/build.py: Python standard-library generator
- /usr/local/sbin/housing-podcast-publish: explicit, locked publication command
- /etc/nginx/snippets/housing-podcast.conf: dedicated URL configuration

Private directories are owned by git, mode 0700. Publishing runs with sudo,
validates media using existing FFprobe, and activates a release only after a
successful build. Build failures leave the previous symlink unchanged.
Only assets referenced by published episode manifests (and the cover) are
copied to the web root. Draft manifests, scripts, originals and unused media
are never copied. Publishing requires a final show name, a square JPG/PNG
cover of 1400–3000 px, a real audio file no longer than 300 seconds, and a
non-future timezone-aware publication date. GUIDs must remain unchanged.

RSS is audio-first with MP3/M4A enclosures. Optional MP4 and TXT/VTT links
appear on the episode page. Upload full videos directly to YouTube; export
vertical excerpts separately for Shorts/Reels. An empty RSS is staging
infrastructure, not a directory-ready show. Directory registration is pending.

## Production workflow

1. Record and upload the original over SSH/SFTP to incoming/ (never web root).
2. Edit the recording; export an MP3/M4A at most five minutes long, an MP4
   for YouTube, and optional vertical excerpts. FFmpeg/FFprobe are installed.
3. Rehearse/review German delivery, edit and check captions. Save final audio
   in media/ under a stable ASCII filename, with optional MP4/transcript.
4. Finalize show.json including provisional_title=false and cover filename.
5. Review episode JSON. Set audio, optional video/transcript, published_at
   (ISO 8601 with timezone) and status=published only for approved content.
6. Run `sudo /usr/local/sbin/housing-podcast-publish` on the NUC.
7. Independently read the HTTPS page/feed and each enclosure; verify MIME,
   HEAD, byte ranges and the enclosure byte length. Register with directories
   only after the final name, cover and at least one real episode exist.
8. Remove noindex from build.py and nginx-location.conf when launching.

Local checks:

```
python3 -m unittest discover -s services/podcast -p 'test_*.py'
python3 services/podcast/build.py --content services/podcast/content \
  --media /path/to/private/media --output /path/to/new-release
```

Rollback: inspect `readlink /var/www/podcast/current` and the saved prior
release first. Create current.next pointing to that release, then atomically
`mv -Tf` it to current. Keep releases until an explicit retention decision.
Do not run website-wide rsync --delete or restore an old full Arroyo snapshot
without preserving this podcast's Nginx include.

## Backup coverage

The existing daily Restic job includes /home/git, /var/www, /etc and
/usr/local/sbin, so private recordings, manifests, releases, Nginx config and
the publication command fall within its source list. The generator source is
also retained in /home/git/podcast/tools and this Git repository because the
job does not include /usr/local/lib. No backup schedule was changed.
Coverage by configuration does not prove a completed backup or restore.

## Sources

- https://podcasters.apple.com/support/823-podcast-requirements
  RSS requirements: actual episodes, artwork, stable GUID, enclosure length,
  public URLs, HEAD and byte-range support (consulted 2026-10-25).
- https://support.google.com/youtube/answer/13525207?hl=en
  Audio RSS ingestion creates a static-image video, not the camera recording.

## Deployment verification — 2026-10-25

Activated release `20261025T164611Z-917057`. Previous Arroyo website snapshot:
`/var/backups/arroyo.ing/podcast-20261025T164611Z`; previous vhost config:
`/etc/nginx/sites-available/arroyo.ing.before-podcast-20261025T164611Z`.
Nginx syntax passed and the service remained active after reload. Independent
HTTPS HEAD requests returned 200 for the page and feed, with text/html and
application/rss+xml respectively. A 32-byte feed request returned 206 with
Content-Range bytes 0-31/711. Five local tests passed, including a real FFmpeg
fixture exercising cover validation and audio enclosure generation, draft
exclusion, unsafe media paths and refusal to overwrite an existing release.
The empty feed is not yet eligible for platform submission.

A temporary one-second MP3 also returned HTTP 200/audio/mpeg and HTTP 206
with Content-Range bytes 0-31/8586 from the public HTTPS endpoint. It was
removed immediately afterward and its URL returned 404. Public requests for
drafts/001-de.md, content/show.json and incoming/ returned 404. The live RSS
parsed successfully and contained zero items; the page/feed body sizes were
933 and 711 bytes. Private backups have configured coverage, not a verified
new snapshot or restore.
