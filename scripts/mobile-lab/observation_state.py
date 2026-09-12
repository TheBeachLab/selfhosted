"""Only newly delivered MQTT measurements may refresh stored sensor values."""
from datetime import datetime, timezone
from threading import Lock
import math

TTL_SECONDS = 300

class ObservationState:
    def __init__(self):
        self.devices = {}
        self.lock = Lock()

    def receive(self, device, field, value, *, retained=False, now=None):
        # Scalar retained messages carry no source time. Broker replay is not
        # evidence that a sensor is alive, even immediately after a restart.
        if retained:
            return
        now = now or datetime.now(timezone.utc)
        with self.lock:
            self.devices.setdefault(device, {})[field] = (value, now)

    def snapshots(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            devices = {device: dict(fields) for device, fields in self.devices.items()}
        result = []
        for device, fields in devices.items():
            fresh = {key: pair for key, pair in fields.items()
                     if 0 <= (now - pair[1]).total_seconds() <= TTL_SECONDS}
            if not fresh:
                continue
            result.append((device, {key: pair[0] for key, pair in fresh.items()},
                           {key: pair[1].isoformat() for key, pair in fresh.items()},
                           max(pair[1] for pair in fresh.values())))
        return result


def finite_float(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

# Whitelisted public fields only. Combined messages never store raw payloads.
GML_FIELDS = {
    'gml/nav': {'lat':'gps_lat', 'lon':'gps_lon', 'speed_kmh':'gps_speed_kmh',
                'satellites':'gps_satellites', 'fix':'gps_fix',
                'gps_altitude_m':'gps_altitude_m', 'altitude_m':'altitude_m',
                'baro_altitude_m':'baro_altitude_m', 'pitch_deg':'imu_pitch_deg',
                'roll_deg':'imu_roll_deg', 'heading_deg':'heading_deg'},
    'gml/cabin': {'co2_ppm':'co2_ppm', 'temp_c':'temperature_c',
                  'humidity_pct':'humidity_pct', 'pressure_hpa':'pressure_hpa'},
    'gml/starlink': {'state':'starlink_state', 'downlink_mbps':'starlink_downlink_mbps',
                     'uplink_mbps':'starlink_uplink_mbps', 'ping_ms':'starlink_ping_ms',
                     'ping_drop_rate':'starlink_ping_drop_rate', 'uptime_s':'starlink_uptime_s',
                     'obstructed':'starlink_obstructed', 'obstruction_pct':'starlink_obstruction_pct'},
}

def gml_fields(topic, payload, now=None):
    """Translate supported public readings, rejecting old store-and-forward nav."""
    import json
    mapping = GML_FIELDS.get(topic)
    if not mapping:
        return {}
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return {}
        if 'ts' in data:
            time = datetime.fromisoformat(data['ts'].replace('Z', '+00:00'))
            age = ((now or datetime.now(timezone.utc)) - time).total_seconds()
            if not 0 <= age <= TTL_SECONDS:
                return {}
        result = {target: data.get(source) for source, target in mapping.items()}
        for field in ('gps_lat', 'gps_lon'):
            if field in result:
                number = finite_float(result[field])
                result[field] = round(number, 2) if number is not None else None
        return result
    except (ValueError, TypeError, AttributeError):
        return {}
