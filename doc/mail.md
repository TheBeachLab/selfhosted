# WIP. Mail servers: Postfix, Dovecot and OpenDKIM

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
