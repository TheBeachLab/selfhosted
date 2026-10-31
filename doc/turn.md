# STUN/TURN server

WIP. On 2026-02-08 `coturn` was disabled and its public firewall rules were
removed ([safeguards](server-safeguards.md)). The notes below are the
unfinished setup.

From <https://ourcodeworld.com/articles/read/1175/how-to-create-and-configure-your-own-stun-turn-server-with-coturn-in-ubuntu-18-04>

`sudo apt-get install coturn`

`nano /etc/default/coturn` make sure `TURNSERVER_ENABLED=1`

Missing correct link of certificates
