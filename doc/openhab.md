# openHAB Server

openHAB connects a BTicino MyHOME/SCS installation to Apple Home through the
OpenWebNet binding and the HomeKit integration.

This is a public operational overview. Network topology, device identifiers,
pairing material, credentials, backup names and the complete accessory inventory
are intentionally not documented here.

## Production baseline

Verified on 2026-08-03:

- openHAB 5.2.1 from the official stable APT repository
- Java 21
- `openhab.service` enabled and active
- OpenWebNet and HomeKit bundles active
- the openHAB package held so upgrades remain manual

openHAB 5 requires a 64-bit Java 21 JDK. Refer to the official
[download page](https://www.openhab.org/download/) and
[Linux installation guide](https://www.openhab.org/docs/installation/linux.html)
before changing versions.

## HomeKit stability

Apple Home stores room assignments, names, icons and favourites on the Apple
controller side. openHAB exposes the accessories but cannot choose their Apple
Home rooms. Keep Item names and HomeKit metadata stable because changing or
removing an accessory can make Apple Home treat it as a different device.

The bridge uses these safeguards:

```properties
startDelay="120"
useDummyAccessories="true"
```

`useDummyAccessories` keeps a placeholder when an Item is temporarily absent,
which helps Apple Home preserve its controller-side configuration. `startDelay`
gives openHAB time to finish loading Items before publishing the bridge. See the
official [HomeKit dummy-accessory documentation](https://www.openhab.org/addons/integrations/homekit/#dummy-accessories).

Do not clear HomeKit pairings or delete the bridge identity during routine
maintenance. Both operations make Apple Home see a new bridge and require a new
pairing and room configuration.

After a restart, Apple Home may briefly show cached `No Response` or `Updating`
states while it reconnects. Validate the bridge before re-pairing it:

1. Confirm the openHAB service is active.
2. Confirm the HomeKit listener is bound to the LAN interface.
3. Confirm `_hap._tcp` advertises the bridge through mDNS.
4. Confirm an Apple controller establishes a TCP session to the HomeKit port.
5. Allow the Apple Home refresh to complete; a transient refresh timeout is not
   proof that the pairing was lost.

## Upgrade procedure

The 2026-08-03 migration ran in two supported steps so the database migration
tools could update each major format in sequence:

1. openHAB 3.3 to 4.3 on Java 17
2. openHAB 4.3 to 5.2 on Java 21

The migration retained the configured Things, Items, channel links, HomeKit
metadata, advertised accessories and Apple pairings. Backups and rollback
packages are retained outside this public repository.

Before another manual upgrade:

```bash
sudo openhab-cli backup --full
sudo unzip -t /var/lib/openhab/backups/<backup>.zip
apt-cache policy openhab
java -version
```

Then install an explicitly selected version and restore the package hold:

```bash
sudo apt-mark unhold openhab
sudo apt-get update
sudo apt-get install openhab=<version>
sudo apt-mark hold openhab
```

The official Linux guide recommends holding the package to avoid accidental
upgrades. Check the target release notes and Java requirements before removing
that hold.

## Operational checks

```bash
systemctl is-active openhab.service
systemctl is-enabled openhab.service
curl -I http://127.0.0.1:8080/
sudo ss -lntup
sudo journalctl -u openhab.service -b
```

Also confirm in the openHAB console that the OpenWebNet and HomeKit bundles are
active, the BTicino gateway Thing is online, the expected accessories are
advertised and no unexpected dummy accessories remain.

Keep credentials, pairing codes, QR codes, bridge identities, controller keys,
private addresses and raw configuration exports out of issues, commits and CI
logs.
