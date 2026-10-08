# Synology DiskStation

## Hardware and DSM

Verified by SSH on 2026-10-08: DS411slim (`DS411slimv10-j`), DSM
6.2.4-25556 Update 8, architecture `88f6282` / `armv5tel`, Linux
2.6.32.12. Sources on the NAS: `/proc/sys/kernel/syno_hw_version`,
`/etc.defaults/VERSION`, `unique` in `/etc.defaults/synoinfo.conf`, and
`uname -m` / `uname -r`.

LAN address at that verification: `192.168.1.100`; DSM HTTP port `5000`,
DSM HTTPS port `5001`, existing DSM OpenSSH port `22222`, SMB port `445`.

## Private access

Connected and verified on 2026-10-08 in tailnet `thebeachlab.github`:

- Name: `diskstation.tail520737.ts.net`
- IPv4: `100.92.107.45`
- DSM: <http://diskstation.tail520737.ts.net:5000/>
- SMB: `smb://100.92.107.45`
- Existing DSM SSH: `ssh -p 22222 unix@100.92.107.45`

Sources: NAS `tailscale status --json` reported `Running`, `Online: true`,
and an empty health list; the Mac's peer list reported the same DNS name
and IP. From the Mac, `tailscale ping 100.92.107.45` used the direct
Tailscale connection. DSM returned HTTP 200 with the DiskStation title;
the MagicDNS URL above also returned HTTP 200. OpenSSH succeeded with the
previously trusted NAS host key
(`-o HostKeyAlias=192.168.1.100 -o StrictHostKeyChecking=yes`). TCP ports
445 and 5001 were reachable. SMB authentication/file access and an HTTPS
certificate check were not performed. These checks used the Tailscale IP
from a Mac on the same LAN; access from a separate external network was
not tested.

Readback of `tailscale debug prefs`: `WantRunning=true`, `CorpDNS=false`,
`RouteAll=false`, no advertised routes, and `RunSSH=false`. The NAS does
not take Tailscale DNS settings, accept other subnet routes, advertise a
subnet, or run Tailscale SSH. The package's DSM enabled flag exists;
a full NAS reboot was not performed to test startup after authentication.

Installation cleanup: the NAS scratch directory
`/volume1/@tmp/nas-tailscale-b23718af` was removed, and Tailscale remained
connected afterward. The temporary root task `Tailscale install b23718af`
remains in DSM Task Scheduler, disabled and prefixed with `exit 0`;
both settings were read back from DSM after saving. It cannot run the
installation commands in that state.

## Tailscale compatibility

The official `88f6282` DSM6 package for 1.104.1 installed successfully,
but its daemon exited with `accept4: function not implemented`. A temporary
userspace daemon probe of the official 1.102.4 binaries reproduced that error.
The same probe of 1.80.3 stayed running and its CLI returned `Logged out`.
These observations establish compatibility for the tested startup path, not
that 1.80.3 is the newest compatible release.

The package reports Go 1.23.5. Go documents Linux 3.2 as its minimum from
Go 1.24; Tailscale separately documented the missing ARM `accept4` syscall
on Synology kernels 2.6.32.12. Sources:
[Go minimum requirements](https://go.dev/wiki/MinimumRequirements),
[Tailscale issue 6792](https://github.com/tailscale/tailscale/issues/6792).

Official package:
[`tailscale-88f6282-1.80.3-600080003-dsm6.spk`](https://dl.tailscale.com/stable/tailscale-88f6282-1.80.3-600080003-dsm6.spk).
SHA-256 checked against the vendor's
[checksum](https://dl.tailscale.com/stable/tailscale-88f6282-1.80.3-600080003-dsm6.spk.sha256):
`0db0efa0326fa40b5e9f106c47ef5ab246dc69ec22cc3f6d3aaed796cbed1828`.

1.80.3 is an old release and lacks later fixes. Check the
[vendor's security bulletins](https://tailscale.com/security-bulletins)
before enabling additional Tailscale features. Do not blindly update this
NAS to the current release: test daemon startup and access first, with a
working LAN/DSM path available for recovery.

For DSM6, the official package runs as root and supplies its own startup
script. The extra DSM7 `configure-host` boot task is not required. Use DSM's
existing SSH server over Tailscale; Tailscale SSH is unsupported on Synology.
Source: [Tailscale Synology documentation](https://tailscale.com/docs/integrations/synology).

The installed 1.80.3 package started successfully on 2026-10-08: the root
installer's `synopkg status Tailscale` returned `Tailscale package is started`,
`/var/packages/Tailscale/enabled` existed, and the daemon remained running.
Use a root DSM context for `synopkg` status checks. The unprivileged SSH user
received status 310 even while `tailscale status` responded and the PID was
alive; that same user could not execute the package's status script.

## Clock and installer precautions

The NAS initially reported January 2000. After the user corrected the clock,
DSM showed the Madrid time zone and NTP server `pool.ntp.org`; SSH returned
the current date. A bad clock was observed, but it was not established as
the sole cause of the DSM login failure.

The package publisher filter rejected the first install with error 290.
Installation required temporarily allowing `Any publisher`, with user
approval. Restore `Synology Inc. and trusted publishers` afterward.
That setting was read back in DSM after the compatible package was installed.
The same filter behavior is documented in
[Tailscale PR 9363](https://github.com/tailscale/tailscale/pull/9363).

`/tmp` is a 122 MiB RAM filesystem on this NAS. Stage large packages in a
private directory under `/volume1/@tmp`, verify their checksums there, and
remove only the task's own temporary files after validation.
