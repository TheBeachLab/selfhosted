# Mail servers: Postfix, Dovecot and OpenDKIM

Postfix on the NUC is disabled. The firewall allow for SMTP was removed and
`postfix` was disabled and left inactive ([safeguards](server-safeguards.md)).
That decommission was recorded on 2026-02-08 (commit `ee6a26b`). The note does
not give a separate earlier disable date. Dovecot and OpenDKIM were never
written up.

Public mail for `beachlab.org` is iCloud, and Hexxan mail is Google, as kept
in the 2026-10-23 Cloudflare migration
([Cloudflare DNS](../services/cloudflare-ddns/README.md)). This page is the
old Postfix install.

<!-- vim-markdown-toc GFM -->

- [Postfix](#postfix)

<!-- vim-markdown-toc -->

## Postfix

Postfix is a MTA mail transfer agent, it receives the emails from the Internet and stores them until you retrieve them.

```bash
sudo apt update
sudo DEBIAN_PRIORITY=low apt install postfix
```

Whenever you need to reconfigure postfix `sudo dpkg-reconfigure postfix`
