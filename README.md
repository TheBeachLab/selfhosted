# Selfhosted

> To become independent, you don't have to  ask for independence. To become independent you have **to be** independent.

This is the story of how I am slowly becoming independent. Disclaimer: If you don't understand anything, that's fine. I created this documentation for myself.

![](img/suitcase.jpg)

## Why am I doing this

My name is Francisco, in french it means "free person" . Some people in life want performance, some other want reliability. The only thing I care about is freedom. To do what I want, when I want and how I want to.

## What hardware do you need

You will be surprised how low-tech this whole thing can go. Of course the better hardware you have the longer you will travel. But for most common needs like website, mail and so, any computer from 10 years ago will be fine. You can even use a raspberry pi and carry your server in your pocket!! 

My first server, called Suitcase was a 2015 Skylake i3-6100 (2 cores/4 threads) @ 3.700GHz with 8GB RAM and 500GB SSD running Ubuntu Server 22.04 LTS. Status: Non Operational

My second server, called Sister was a X79 chipset with a liquid cooled Intel Xeon E5-2670 v2 (10 cores/20 threads) @2.500Ghz with 40GB RAM and 1TB NVME SSD running Ubuntu Server 22.04 LTS. Status: Non Operational

My third server is an Intel NUC 11. Not so powerful as the above but quite compact and portable. 16Gb RAM 

The Internet line is a 1000Mbps symmetric FTTH with dynamic IP address.

- TODO: Convert a powerbank to 12V UPS for the router using a [Pololu Adjustable Boost Regulator 4-25V](https://www.pololu.com/product/799/specs)

## TOC

- [Getting started](doc/getstarted.md)
- [Securing SSH access](doc/security.md)
- [Backups](doc/backups.md)
- [Web server](doc/web.md)
- [NodeJS Server](doc/nodejs.md)
- [Git server](doc/git.md)
- [SFTP server](doc/sftp.md)
- [Transmission Daemon](doc/transmission.md)
- [Mumble server](doc/mumble.md)
- [VPN Server](doc/vpn.md)
- [Wireguard VPN](doc/wireguard.md)
- [iOS Push Notifications iGotify](doc/igotify.md)
- [n8n Server](doc/n8n.md)
- [OpenHab Server](doc/openhab.md)
- [Auto USB copy](doc/transfer2usb.md)
- [Troubleshooting](doc/troubleshooting.md)
- [OpenClaw TUI Quick Access (tmux)](doc/openclaw-tui.md)
- [Server Safeguards (resource limits + alerts)](doc/server-safeguards.md)

IoT and Databases
- [IoT related](doc/iot.md)
- [MQTT Telemetry (alpha/stats)](doc/mqtt-telemetry.md)
- [MQTT to TimescaleDB and PostgREST (1-Month History)](doc/mqtt-timescale-postgrest.md)
- [PostgreSQL Database Server](doc/postgres.md)
  - [TimescaleDB](doc/timescaledb.md)
  - [Strapi CSM](doc/strapi.md)
  - [PostgREST API](doc/postgrest.md)
  - [PostgREST JWT Gateway](doc/postgrest-jwt.md)
  - [OSM Server](doc/osm.md)
  - [Working with CSV](doc/csv.md)
- [Open Geo Data](doc/geodata.md)
  - [Spanish CNIG MDT02 Bulk Download to Synology NAS](doc/mdt02-spain.md)
  - [Hybrid Tiles Pipeline (Vector + Raster)](doc/tiles-hybrid.md)
  - [Planet Basemap Ops (PMTiles/MBTiles)](doc/planet-basemap.md)
  - [Airports Database](doc/airports.md)
  - [Baustellen in München](doc/baustellen.md)

AI Related
- [GPU](doc/gpu.md)
- [GPU Service Management (on-demand Whisper/RAG/TTS)](doc/gpu-services.md)
- [Whisper Web (protected upload + diarization)](doc/whisper.md)
- [High-Precision eBook RAG (SFTP Inbox)](doc/rag-library.md)
- [Qwen3-TTS Voice Cloning (multilingual)](doc/qwen3-tts.md)


To improve or fix
- [Understanding DNS](doc/dns.md)
- [Taskserver](doc/taskserver.md)
- [OBS ninja](doc/obsninja.md)
- [STUN/TURN Server (WIP)](doc/turn.md)
- [Minecraft server](doc/minecraft.md)
- [Cloud server](doc/cloud.md)
- [Mail server](doc/mail.md)

