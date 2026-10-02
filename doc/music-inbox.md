# Music inbox

Upload songs or album folders to **Music/imported** in Nextcloud.
The server checks completed uploads five minutes after the previous run finishes. Confident matches move
to **Music/Album artist/Album/Track - Title.ext**. Uncertain matches stay in the
inbox. **Music/import-status.md** shows progress and pending files without SSH.
Amperfy consumes the Nextcloud Music index, which is refreshed after processing.

## Recognition and limits

The runtime uses [beets](https://docs.beets.io/en/latest/guides/tagger.html) 2.14.0. The Apple catalog supplies strict
artist/title/duration matches first. MusicBrainz provides additional recording/release
metadata when reachable; [AcoustID fingerprints](https://docs.beets.io/en/latest/plugins/chroma.html)
supplement uncertain matches and
can supply recording identities even when MusicBrainz search is unavailable. Beets
automatic acceptance requires a strong recommendation, distance <= 0.05, a margin
of at least 0.02 over the next candidate, complete source mappings, and track
duration differences <= 3 seconds. Different live/remix/edit markers and AI,
karaoke, instrumental, remake or stem labels require review. These are local
conservative thresholds, not guarantees supplied by MusicBrainz. Apple matches
require artist and title similarity >= 0.94, duration difference <= 3 seconds,
and matching version markers. The original album is preserved unless its title
matches the catalog album at >= 0.9. Catalog evidence is stored with proposals.
Apple requests are cached and spaced at least 3.2 seconds apart, following its
[documented approximate 20/minute limit](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).

For loose tracks and unmatched tracks within albums, direct AcoustID acceptance requires a single consistent
artist/title identity, duration difference <= 3 seconds, score gap >= 0.05,
and score >= 0.98 (or >= 0.95 with matching existing artist/title hints).
Version markers must agree. Fingerprints are looked up, not submitted to the
database. Recording matches never select an arbitrary release from the list.
Partial album matches also produce separate, independently reviewable fingerprint
proposals for the remaining tracks.

MusicBrainz returned intermittent HTTP 503 responses during the initial import.
The worker bounds lookups and falls back when the provider fails.
The pinned beets HTTP client defaults to six retries (installed source:
`beetsplug/_utils/requests.py`, `TimeoutAndRetrySession`). This worker disables
those inline retries and stops MusicBrainz fallback for the remainder of a run
after HTTP 429/5xx. The scheduler retries later. Already approved source hashes
skip recognition and proceed to processing without repeating provider lookups.

Albums are matched together. Loose songs are matched individually; without
reliable album metadata they go to Singles. Existing cover art is retained;
missing covers come from the matched release's
[Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API) entry,
or the matching Apple album's supplied artwork URL, and embedded. Existing
art is never replaced with the smaller Apple image. Files are never transcoded.
FFprobe supplements beets' reads for nonstandard uppercase MP4 metadata, verified
on this collection's ALAC files. CD suffixes are normalized for multidisc matching.

The Nextcloud 32 integration uses its file API to keep the cache in sync.

## Runtime and recovery

- Code/venv: `/opt/music-inbox` (root owned).
- State: `/var/lib/music-inbox` (www-data, not web accessible).
- Scheduler: `music-inbox.timer`, `music-inbox.service`.
- Collection root: `/Music/`; inbox: `/Music/imported/`.
- `proposals`: source hashes, matching evidence, proposed tags and destinations.
- `review.json`: explicit initial review decisions keyed by proposal filename stem.
- `originals`: verified originals before tag writes, keyed by SHA-256.
- `preflight-originals`: snapshot before the initial reorganization.
- `done`: original source IDs/hashes and resulting IDs/paths/hashes.
- `errors`: actionable per-file failures. No original is deleted on collision.

The lock prevents concurrent runs. Uploads must be at least two minutes old and
unchanged while hashed. Rejected proposals retry after seven days; lookup errors
retry after one hour. A changed group/content hash triggers a new proposal.
Writes require the original file ID to remain under imported and its hash to
match. A staged tagged copy must preserve the encoded audio-stream hash. The
Nextcloud bridge checks destination collisions and writes/moves using the same
file node, preserving its ID. Original backups have no automatic deletion.

If interrupted after a tag write but before a move, the original is still backed
up, the source remains in imported, and the next scan treats the new content as
a new proposal. No timer should be enabled until the initial proposals have been
reviewed and the end-to-end move has been verified.

Operator diagnostics: `journalctl -u music-inbox.service`, the state files above,
and `php /var/www/nextcloud/occ music:scan admin --folder=Music` as www-data.
Stop the timer to pause ingestion. Restore content through the Nextcloud file
API using the saved original, then refresh Music; do not restore a whole database
or overwrite later user changes.

An identity-only review decision keeps the original version labels, co-credits,
album, numbering and recording IDs when the fingerprint agrees on artist/title
but gives conflicting editions. It does not apply the suggested edition metadata.
These decisions are marked in `review.json` and the per-file receipts.
Later uploads use the matching thresholds above.

## Deployment

This installation targets the existing native Nextcloud service on `pink-sudo`,
with Python 3.10, PHP, FFmpeg and `libchromaprint-tools`. Install the pinned
`requirements.lock` into `/opt/music-inbox/venv`; deploy the adjacent Python/PHP
files root-owned and readable by www-data. Create `/var/lib/music-inbox` owned by
www-data and install the two systemd units under `/etc/systemd/system`.

Run `venv/bin/python -m unittest -v test_organize` in `/opt/music-inbox` and
`php -l bridge.php`. The tests include real ALAC tag writes and encoded-audio
preservation, conflicting fingerprint identities, artist-credit formatting,
compilation fallback, and path/version guards. The commissioning bridge checks
also reject a real occupied destination and stale source hash without changing
either existing file.

The `initialize` bridge operation is a one-time migration of the existing library
to imported; **do not repeat it on an organized library**. Take a verified original
snapshot first. Use `organize.py scan`, review proposals, and `organize.py apply`
as www-data with the same environment as the service. Only after successful review
and end-to-end checks, enable `music-inbox.timer`. All subsequent user interaction
is through the Nextcloud inbox and status document.

## Amperfy artwork compatibility — 2026-09-10

Amperfy 2.1.1 build 22 was observed requesting
`/apps/music/ampache/image.php?auth=…&object_id=…&object_type=album`.
Music 3.2.1's installed `lib/Controller/AmpacheImageController.php::image`
accepts an image-specific `token`, not session `auth`. Without `token` it
returns a 2,330-byte generic PNG with a one-year client cache lifetime.
This explains why an ordinary library sync did not repair the artwork.
`AmpacheController::get_art` returns the image through session authentication.

Deploy `services/music-inbox/ampache-images.nginx.conf` to
`/etc/nginx/snippets/music-ampache-images.conf` and include it inside the
Nextcloud TLS server block **before** the PHP regex location. It routes only
session-auth image requests to the existing authenticated `get_art` action.
Image-specific tokens and anonymous placeholder requests retain their original
route. `REQUEST_URI` and `QUERY_STRING` must both identify the authenticated
action; rewriting the path alone does not change Nextcloud's route selection.
This avoids editing the signed Music application or bypassing authentication.
Run `nginx -t` before reloading. Remove the include and reload to roll back.

In Amperfy on the Mac, refresh the cache through Settings > Artwork, then
Account > Resync Library. Clear downloaded artwork if the old generic image
remains. Downloaded songs can stay.

## Mac drop folder

The macOS client, LaunchAgent, tests, and installation instructions live in
`myComputing/mac/music-inbox/`. See the sibling repository
[Music Inbox for macOS](../../myComputing/mac/music-inbox/README.md).

This repository owns the server receiver, `services/music-inbox/receive-drop.php`,
installed at `/opt/music-inbox/receive-drop.php`. It accepts uploads from the Mac
over the existing `pink-sudo` SSH connection and writes through Nextcloud's file
API as www-data. Verified transfer receipts are stored in
`/var/lib/music-inbox/drop-receipts`; the destination is `Music/imported`.
The server recognition service then organizes accepted tracks as described above.
