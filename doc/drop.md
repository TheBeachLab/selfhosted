# Downloads and Drop

Open [beachlab.org/downloads](https://beachlab.org/downloads/) with an
[Authentik passkey](authentik.md). The old `/drop/` URL opens the same page.

I can browse folders, download files, delete files or folders, and add a public
HTTP/HTTPS URL. Deletion asks for confirmation and is permanent. Drop gives new
downloads random names while keeping the extension.

Hidden folders, `.incomplete`, `.part`, `.crdownload`, symlinks and special files
are hidden. Deleting a file does not remove its Transmission entry; remove that
there too if it is no longer needed.

## Shared folder

Transmission, Drop and Chromium use `/home/pink/downloads`:

- Transmission mounts it as `/downloads`.
- Chromium mounts it as `/config/Downloads` in
  [browser-compose.yml](../services/browser-compose.yml).
  `download.default_directory=/config/Downloads` and
  `prompt_for_download=false` select it.
- [drop.service](../services/drop.service) runs as `pink:www-data`.
  `BindPaths` exposes the folder as `/var/lib/url-drop/files` inside the
  service. `DROP_DIR` points there; `ProtectHome=true` hides the other home
  folders.

Only Transmission uses NordVPN. Sharing a folder does not put Drop or Chromium
through its VPN.

## Install and maintain

The application is [drop.py](../services/drop.py), service `url-drop`.
Its socket is `/run/url-drop/url-drop.sock`, mode 0660, owner `pink:www-data`.

Install [downloads-nginx.conf](../services/downloads-nginx.conf) as
`/etc/nginx/snippets/downloads.conf` inside Beachlab's HTTPS server.
Remove the old `/drop/` and `/drop-internal/` blocks when adding the include.
Files are delivered with X-Accel-Redirect, `internal`, `disable_symlinks on`,
attachment headers and CSP sandbox.

Give Nginx read access without changing file owners:

```bash
sudo setfacl -R -m u:www-data:rX /home/pink/downloads
sudo find /home/pink/downloads -type d -exec setfacl -m d:u:www-data:rx {} +
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl restart url-drop
sudo systemctl reload nginx
```

Keep the ACLs when adding files with other tools. Directory descriptors and
O_NOFOLLOW prevent symlink escapes; recursive deletion supports Python 3.10.

POST requires JSON and `X-Drop-Request: 1` and rejects foreign Origin and
cross-site Sec-Fetch-Site headers. Nginx handles user authorization. Keep the
socket private.

The downloader limits files to 20 GiB, reserves 5 GiB free space and runs two
jobs at a time. It checks public destinations at every redirect, and systemd
blocks private networks.

Read errors with `journalctl -u url-drop`. Check the service with
`systemctl status url-drop`.

The previous configuration is backed up at
`/opt/url-drop/backups/20260914T123117/`. Check for later changes before restoring
it, and keep the shared downloads folder.
