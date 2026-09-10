# Music inbox

User workflow: upload songs or album folders to **Music/imported** in Nextcloud.
The server checks completed uploads five minutes after the previous run finishes. Confident matches move
to **Music/Album artist/Album/Track - Title.ext**. Uncertain matches stay in the
inbox. **Music/import-status.md** shows progress and pending files without SSH.
Amperfy consumes the Nextcloud Music index, which is refreshed after processing.

## Recognition and limits

The runtime is pinned to beets 2.14.0. The Apple catalog supplies strict
artist/title/duration matches first. MusicBrainz provides additional recording/release
metadata when reachable; AcoustID fingerprints supplement uncertain matches and
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

At commissioning, MusicBrainz returned intermittent HTTP 503 responses from both
the server and Mac; this is a live observation, not a permanent availability claim.
The worker bounds lookups and falls back without inventing recording identities.
The pinned beets HTTP client defaults to six retries (installed source:
`beetsplug/_utils/requests.py`, `TimeoutAndRetrySession`). This worker disables
those inline retries and stops MusicBrainz fallback for the remainder of a run
after HTTP 429/5xx. The scheduler retries later. Already approved source hashes
skip recognition and proceed to processing without repeating provider lookups.

Albums are matched together. Loose songs are matched individually; without
reliable album metadata they go to Singles. Existing cover art is retained;
missing covers are fetched from the matched release's Cover Art Archive entry,
or the matching Apple album's supplied artwork URL, and embedded. Existing
art is never replaced with the smaller Apple image. Files are never transcoded.
FFprobe supplements beets' reads for nonstandard uppercase MP4 metadata, verified
on this collection's ALAC files. CD suffixes are normalized for multidisc matching.

Sources: [beets tagging](https://docs.beets.io/en/latest/guides/tagger.html),
[fingerprinting](https://docs.beets.io/en/latest/plugins/chroma.html),
[Cover Art Archive API](https://musicbrainz.org/doc/Cover_Art_Archive/API).
The installed Nextcloud 32 Music service and filesystem APIs are the authority
for integration; this implementation calls the file API rather than renaming
files behind Nextcloud's cache.

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

The first batch is reviewed by the assistant against external matching evidence.
Where fingerprints corroborate the source's artist/title but contain conflicting
edition associations, supervised identity-only decisions retain the original
version labels, co-credits, album, numbering and recording IDs. They do not apply
the suggested fingerprint metadata or claim independent verification of the
edition. These decisions and their evidence are distinguished in `review.json`,
the per-file receipts and the Nextcloud status report.
The ongoing service uses deterministic thresholds; it does not claim an LLM
reviews every future upload or manufacture facts about unidentified recordings.

## Commissioning evidence — 2026-09-10

The live native service on `pink-sudo` completed successfully under systemd on
2026-09-10 at 17:13 UTC, with the timer enabled and active. Read-back evidence:
`/var/lib/music-inbox/commissioning-verification.json`, per-file `done` receipts,
`review.json`, `bridge-checks.json`, the service journal and the Nextcloud database.

- 475 audio files remain in Music: 422 organized, 53 pending in imported,
  including one existing empty file.
- All 422 final-file hashes and all 422 original-backup hashes matched their
  receipts; all 422 file IDs were preserved. Verification reported zero errors.
- 392 organized files have embedded artwork, including artwork already present.
- 68 organized files used the supervised source-metadata-preserving decisions
  described above; their exact editions were not independently verified.
- Nextcloud Music still contains 475 distinct admin tracks and file IDs, with
  the original track-ID range 1–475. Collection setting read back as `/Music/`.
- Nine tests passed in the pinned server environment, alongside PHP syntax
  validation and the live bridge collision/stale-hash rejection checks.

These are commissioning observations, not permanent counts. The status document
in Nextcloud is the current user-facing view.

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
The authenticated `AmpacheController::get_art` returned the real image for
the same album and session. These are observations of the installed source
and HTTPS responses, not assumptions about the client cache.

Deploy `services/music-inbox/ampache-images.nginx.conf` to
`/etc/nginx/snippets/music-ampache-images.conf` and include it inside the
Nextcloud TLS server block **before** the PHP regex location. It routes only
session-auth image requests to the existing authenticated `get_art` action.
Image-specific tokens and anonymous placeholder requests retain their original
route. `REQUEST_URI` and `QUERY_STRING` must both identify the authenticated
action; rewriting the path alone does not change Nextcloud's route selection.
This avoids editing the signed Music application or bypassing authentication.
Run `nginx -t` before reloading. Remove the include and reload to roll back.

Live checks in `/var/lib/music-inbox/ampache-cover-verification.json` verified
three album images byte-for-byte against `get_art`, token-based URLs, the
`index.php` URL variant, invalid-session rejection (Ampache XML error), and
anonymous placeholders. Nginx configuration validation passed. The Mac Amperfy
cache was refreshed via Settings > Artwork, then Account > Resync Library;
album covers were visibly displayed in the app after the correction.
Clients that cached the old generic image may need their downloaded artwork
cache cleared; this does not require deleting downloaded songs.
