# Ongoing and past troubleshooting

## Computer shutdowns after exactly 20 minutes

This started happenning when I replaced the Nvidia drivers from nvidia page with the ones in the ubuntu repository. I issue the command `watch uptime` and everytime after 20 minutes, the computer shut downs.

Action | Result
---|---
Vacuum the suitcase | Same
Reseat all connectors and components | Same
Remove the GPU | Same
Disable WoL | Same
Change power supply | Same
Remove cuda 11.1 and nvidia 455 | Same
Check BIOS settings | Done (1)
Check crontabs | Nothing scheduled
`shutdown -c` | Same
Replace CMOS battery | TODO
Without HDD | **It stays on**
With USB Live Ubuntu | **It stays on**
(1) Wake by LAN card was disabled. I reenabled it

That confirms to be a software issue. I remember when I installed the nvidia drivers. Something related with Xorg and gnome-shell. Let's see what I can do there. In fact now when I log in with screen and keyboard it jumps to gnome login screen. Maybe it was not shut down. Could it be that if you don't log in in 20 minutes it hybernates? I did not realise because the server is headless.

`sudo apt purge gnome-shell && sudo apt autoremove`

> **SOLVED!** Removing gnome-shell solved the issue!
