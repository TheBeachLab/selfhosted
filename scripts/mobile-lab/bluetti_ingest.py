#!/usr/bin/env python3
"""
Bluetti MQTT → TimescaleDB ingestor.
Subscribes to bluetti/state/+/<field>, aggregates fields per device,
and writes a row every FLUSH_INTERVAL seconds.
"""
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from threading import Timer
from observation_state import ObservationState, finite_float, gml_fields, GML_FIELDS

import paho.mqtt.client as mqtt
import psycopg

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("bluetti-ingest")

DB_DSN        = os.getenv("DB_DSN", "")
MQTT_HOST     = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
FLUSH_INTERVAL = int(os.getenv("FLUSH_INTERVAL", "30"))  # seconds

INSERT_SQL = """
INSERT INTO public.bluetti_stats (
  time, device_id, field_received_at,
  battery_percent,
  dc_input_power, ac_input_power,
  ac_output_power, dc_output_power,
  power_generation,
  ac_output_on, dc_output_on,
  pack_details1, pack_details2,
  co2_ppm, temperature_c, humidity_pct, pressure_hpa,
  starlink_state, starlink_downlink_mbps, starlink_uplink_mbps,
  starlink_ping_ms, starlink_ping_drop_rate, starlink_uptime_s,
  starlink_obstructed, starlink_obstruction_pct,
  starlink_gps_sats, starlink_country,
  starlink_azimuth_deg, starlink_elevation_deg, starlink_tilt_deg,
  starlink_alerts,
  gps_lat, gps_lon, gps_speed_kmh, gps_altitude_m,
  gps_satellites, gps_fix, heading_deg,
  altitude_m, baro_altitude_m,
  imu_pitch_deg, imu_roll_deg, imu_yaw_rate_dps,
  obd_rpm, obd_speed_kmh, obd_throttle_pct, obd_engine_load_pct,
  obd_boost_kpa, obd_coolant_temp_c, obd_intake_temp_c, obd_oil_temp_c,
  obd_fuel_level_pct, obd_fuel_rail_pressure_kpa, obd_maf_gps,
  obd_runtime_s, obd_voltage_v, obd_dtc_count, obd_connected
) VALUES (
  %(time)s, %(device_id)s, %(field_received_at)s,
  %(battery_percent)s,
  %(dc_input_power)s, %(ac_input_power)s,
  %(ac_output_power)s, %(dc_output_power)s,
  %(power_generation)s,
  %(ac_output_on)s, %(dc_output_on)s,
  %(pack_details1)s, %(pack_details2)s,
  %(co2_ppm)s, %(temperature_c)s, %(humidity_pct)s, %(pressure_hpa)s,
  %(starlink_state)s, %(starlink_downlink_mbps)s, %(starlink_uplink_mbps)s,
  %(starlink_ping_ms)s, %(starlink_ping_drop_rate)s, %(starlink_uptime_s)s,
  %(starlink_obstructed)s, %(starlink_obstruction_pct)s,
  %(starlink_gps_sats)s, %(starlink_country)s,
  %(starlink_azimuth_deg)s, %(starlink_elevation_deg)s, %(starlink_tilt_deg)s,
  %(starlink_alerts)s,
  %(gps_lat)s, %(gps_lon)s, %(gps_speed_kmh)s, %(gps_altitude_m)s,
  %(gps_satellites)s, %(gps_fix)s, %(heading_deg)s,
  %(altitude_m)s, %(baro_altitude_m)s,
  %(imu_pitch_deg)s, %(imu_roll_deg)s, %(imu_yaw_rate_dps)s,
  %(obd_rpm)s, %(obd_speed_kmh)s, %(obd_throttle_pct)s, %(obd_engine_load_pct)s,
  %(obd_boost_kpa)s, %(obd_coolant_temp_c)s, %(obd_intake_temp_c)s, %(obd_oil_temp_c)s,
  %(obd_fuel_level_pct)s, %(obd_fuel_rail_pressure_kpa)s, %(obd_maf_gps)s,
  %(obd_runtime_s)s, %(obd_voltage_v)s, %(obd_dtc_count)s, %(obd_connected)s
)
ON CONFLICT (device_id, time) DO NOTHING;
"""

# In-memory state: {device_id: {field: value}}
state = ObservationState()
conn = None
INGEST_FIELDS = {'heading_deg', 'imu_yaw_rate_dps', 'imu_pitch_deg', 'starlink_uplink_mbps', 'gps_speed_kmh', 'obd_throttle_pct', 'gps_lat', 'altitude_m', 'starlink_ping_drop_rate', 'obd_dtc_count', 'obd_engine_load_pct', 'obd_runtime_s', 'baro_altitude_m', 'dc_output_power', 'dc_input_power', 'gps_altitude_m', 'starlink_ping_ms', 'starlink_state', 'co2_ppm', 'starlink_tilt_deg', 'gps_lon', 'starlink_country', 'pack_details1', 'obd_fuel_level_pct', 'total_battery_percent', 'obd_voltage_v', 'gps_satellites', 'starlink_downlink_mbps', 'starlink_obstructed', 'obd_oil_temp_c', 'temperature_c', 'starlink_elevation_deg', 'obd_fuel_rail_pressure_kpa', 'pressure_hpa', 'ac_input_power', 'humidity_pct', 'starlink_azimuth_deg', 'obd_speed_kmh', 'obd_rpm', 'starlink_gps_sats', 'obd_connected', 'ac_output_on', 'starlink_uptime_s', 'starlink_alerts', 'obd_boost_kpa', 'ac_output_power', 'obd_maf_gps', 'gps_fix', 'starlink_obstruction_pct', 'obd_coolant_temp_c', 'obd_intake_temp_c', 'dc_output_on', 'power_generation', 'pack_details2', 'imu_roll_deg'}


def get_conn():
    global conn
    try:
        if conn is None or conn.closed:
            raise Exception("closed")
        conn.execute("SELECT 1")
    except Exception:
        log.info("Reconnecting to database...")
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        conn = psycopg.connect(DB_DSN)
        conn.autocommit = True
    return conn


def to_float(v):
    return finite_float(v)


def to_int(v):
    try:
        return int(float(v)) if v not in (None, "", "null") else None
    except Exception:
        return None


def to_bool(v):
    if v is None:
        return None
    value = str(v).strip().upper()
    if value in ("ON", "1", "TRUE", "YES"): return True
    if value in ("OFF", "0", "FALSE", "NO"): return False
    return None


def to_json(v):
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        return json.dumps(v)
    try:
        json.loads(v)  # validate
        return v
    except Exception:
        return None


def flush():
    """Write current state snapshot to DB for each known device."""
    # Timestamp the last real delivery, not the flush clock. Repeated
    # snapshots have the same unique key and cannot manufacture new history.
    for device_id, fields, received_at, sample_time in state.snapshots():
        row = {
            "time":             sample_time,
            "field_received_at": json.dumps(received_at),
            "device_id":        device_id,
            "battery_percent":  to_float(fields.get("total_battery_percent")),
            "dc_input_power":   to_float(fields.get("dc_input_power")),
            "ac_input_power":   to_float(fields.get("ac_input_power")),
            "ac_output_power":  to_float(fields.get("ac_output_power")),
            "dc_output_power":  to_float(fields.get("dc_output_power")),
            "power_generation": to_float(fields.get("power_generation")),
            "ac_output_on":     to_bool(fields.get("ac_output_on")),
            "dc_output_on":     to_bool(fields.get("dc_output_on")),
            "pack_details1":    to_json(fields.get("pack_details1")),
            "pack_details2":    to_json(fields.get("pack_details2")),
            # I2C sensors
            "co2_ppm":          to_float(fields.get("co2_ppm")),
            "temperature_c":    to_float(fields.get("temperature_c")),
            "humidity_pct":     to_float(fields.get("humidity_pct")),
            "pressure_hpa":     to_float(fields.get("pressure_hpa")),
            # Starlink
            "starlink_state":            fields.get("starlink_state"),
            "starlink_downlink_mbps":    to_float(fields.get("starlink_downlink_mbps")),
            "starlink_uplink_mbps":      to_float(fields.get("starlink_uplink_mbps")),
            "starlink_ping_ms":          to_float(fields.get("starlink_ping_ms")),
            "starlink_ping_drop_rate":   to_float(fields.get("starlink_ping_drop_rate")),
            "starlink_uptime_s":         to_float(fields.get("starlink_uptime_s")),
            "starlink_obstructed":       to_bool(fields.get("starlink_obstructed")),
            "starlink_obstruction_pct":  to_float(fields.get("starlink_obstruction_pct")),
            "starlink_gps_sats":         to_float(fields.get("starlink_gps_sats")),
            "starlink_country":          fields.get("starlink_country"),
            "starlink_azimuth_deg":      to_float(fields.get("starlink_azimuth_deg")),
            "starlink_elevation_deg":    to_float(fields.get("starlink_elevation_deg")),
            "starlink_tilt_deg":         to_float(fields.get("starlink_tilt_deg")),
            "starlink_alerts":           fields.get("starlink_alerts"),
            # GPS
            "gps_lat":              round(to_float(fields.get("gps_lat")), 2) if to_float(fields.get("gps_lat")) is not None else None,
            "gps_lon":              round(to_float(fields.get("gps_lon")), 2) if to_float(fields.get("gps_lon")) is not None else None,
            "gps_speed_kmh":        to_float(fields.get("gps_speed_kmh")),
            "gps_altitude_m":       to_float(fields.get("gps_altitude_m")),
            "gps_satellites":       to_int(fields.get("gps_satellites")),
            "gps_fix":              to_int(fields.get("gps_fix")),
            "heading_deg":          to_float(fields.get("heading_deg")),
            # Altitude (fused + barometric)
            "altitude_m":           to_float(fields.get("altitude_m")),
            "baro_altitude_m":      to_float(fields.get("baro_altitude_m")),
            # IMU
            "imu_pitch_deg":        to_float(fields.get("imu_pitch_deg")),
            "imu_roll_deg":         to_float(fields.get("imu_roll_deg")),
            "imu_yaw_rate_dps":     to_float(fields.get("imu_yaw_rate_dps")),
            # OBD2
            "obd_rpm":                    to_float(fields.get("obd_rpm")),
            "obd_speed_kmh":              to_float(fields.get("obd_speed_kmh")),
            "obd_throttle_pct":           to_float(fields.get("obd_throttle_pct")),
            "obd_engine_load_pct":        to_float(fields.get("obd_engine_load_pct")),
            "obd_boost_kpa":              to_float(fields.get("obd_boost_kpa")),
            "obd_coolant_temp_c":         to_float(fields.get("obd_coolant_temp_c")),
            "obd_intake_temp_c":          to_float(fields.get("obd_intake_temp_c")),
            "obd_oil_temp_c":             to_float(fields.get("obd_oil_temp_c")),
            "obd_fuel_level_pct":         to_float(fields.get("obd_fuel_level_pct")),
            "obd_fuel_rail_pressure_kpa": to_float(fields.get("obd_fuel_rail_pressure_kpa")),
            "obd_maf_gps":               to_float(fields.get("obd_maf_gps")),
            "obd_runtime_s":              to_int(fields.get("obd_runtime_s")),
            "obd_voltage_v":              to_float(fields.get("obd_voltage_v")),
            "obd_dtc_count":              to_int(fields.get("obd_dtc_count")),
            "obd_connected":              to_bool(fields.get("obd_connected")),
        }
        try:
            with get_conn().cursor() as cur:
                cur.execute(INSERT_SQL, row)
            log.info("Flushed %s — battery: %s%%", device_id, row["battery_percent"])
        except Exception as e:
            log.exception("DB write failed for %s: %s", device_id, e)

    schedule_flush()


def schedule_flush():
    t = Timer(FLUSH_INTERVAL, flush)
    t.daemon = True
    t.start()


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("Connected to MQTT %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe("bluetti/state/#", qos=1)
        client.subscribe("bluetti/+/state/+", qos=1)
        for topic in GML_FIELDS:
            client.subscribe(topic, qos=1)
    else:
        log.error("MQTT connect failed rc=%s", rc)


def on_message(client, userdata, msg):
    if msg.retain:
        return
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    if msg.topic in GML_FIELDS:
        for field, value in gml_fields(msg.topic, payload).items():
            state.receive("AC200M-2241000242252", field, value)
        return
    # Support both legacy scalars and upstream Bluetti's current topic layout.
    parts = msg.topic.split("/")
    if len(parts) != 4 or parts[0] != "bluetti":
        return
    if parts[1] == "state":
        device_id, field = parts[2:]
    elif parts[2] == "state":
        device_id, field = parts[1], parts[3]
    else:
        return
    # Accept only fields consumed by the row mapper; combined/raw payloads
    # and arbitrary topics must not make an otherwise offline device fresh.
    if field not in INGEST_FIELDS:
        return
    value = msg.payload.decode("utf-8", errors="replace").strip()
    state.receive(device_id, field, value, retained=bool(msg.retain))


def shutdown(signum, frame):
    log.info("Shutting down (signal %s)", signum)
    flush()
    try:
        client.disconnect()
    except Exception:
        pass
    try:
        if conn:
            conn.close()
    except Exception:
        pass
    sys.exit(0)


def main():
    global client
    if not DB_DSN:
        raise RuntimeError("DB_DSN is required")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    schedule_flush()
    log.info("Bluetti ingestor started — flush every %ds", FLUSH_INTERVAL)
    client.loop_forever()

if __name__ == "__main__":
    main()
