# Raspberry Pi 5 — pibot1

**Author:** Fran

## Overview

pibot1 is a Raspberry Pi 5 mounted in the G Mobile Lab (vehicle). It runs sensor collection, a Bluetti BLE bridge, Starlink monitoring, and publishes everything to the server via MQTT.

## Hardware

| Component | Interface |
|---|---|
| Raspberry Pi 5 | host |
| K30 CO2 sensor | I2C |
| BME280 temp/humidity/pressure | I2C |
| GPS NEO-6M | serial |
| IMU MPU-6050 | I2C |
| Bluetti AC200M | BLE |

## Network

- **Tailscale IP:** `100.123.199.49`
- **SSH user:** `operator` (via Tailscale SSH)

WiFi priority (NetworkManager, higher = preferred):

| Priority | SSID |
|---|---|
| 40 | Alpen Starlink |
| 30 | Livebox6s-A2EB |
| 20 | Vodafone-F95C |
| 10 | iPhone Fran |

## Services

### bluetti-mqtt

BLE bridge to the Bluetti AC200M (device `D6:FD:4B:1F:E4:12`). Reads battery state, input/output watts, and publishes to MQTT.

### pibot-sensors

Reads I2C sensors (CO2, BME280, IMU), GPS, and Starlink gRPC status. Publishes every 30 s; IMU runs at 2-5 Hz.

### starlink-watcher

Fast Starlink state-change detector. Polls every 5 s, publishes only when state changes.

### prefer-starlink.timer

Systemd timer that reconnects to the Starlink WiFi every 2 min if the SSID is available.

## Key paths

| Path | Purpose |
|---|---|
| `/opt/pibot-sensors/sensor_mqtt.py` | Main sensor collection script |
| `/opt/pibot-sensors/starlink_watcher.py` | Starlink state watcher |
| `/opt/pibot-sensors/imu_calibration.json` | IMU calibration offsets |
| `/etc/NetworkManager/dispatcher.d/99-mqtt-notify` | NM dispatcher hook |

## Quick checks

```bash
ssh operator@100.123.199.49
systemctl status bluetti-mqtt pibot-sensors starlink-watcher
journalctl -u pibot-sensors -n 20 --no-pager
```

## Cross-references

- Server-side telemetry pipeline: see [bluetti-telemetry.md](bluetti-telemetry.md)
- MQTT broker setup: see [iot.md](iot.md)
- WireGuard tunnel: see [wireguard.md](wireguard.md)

## MAVROS Docker (legacy)

### Calibrate stereo cameras

```bash
docker ps
docker exec -it mavros bash

apt update
apt install -y ros-humble-camera-calibration ros-humble-v4l2-camera
```

Launch the nodes:

```bash
ros2 run v4l2_camera v4l2_camera_node --ros-args -r image:=/left/image_raw  --param video_device:=/dev/video12
ros2 run v4l2_camera v4l2_camera_node --ros-args -r image:=/right/image_raw --param video_device:=/dev/video13
```

Run the calibrator:

```bash
ros2 run camera_calibration cameracalibrator \
  --size 9x6 --square 0.025 \
  left:=/left/image_raw right:=/right/image_raw \
  left_camera:=/left right_camera:=/right
```
