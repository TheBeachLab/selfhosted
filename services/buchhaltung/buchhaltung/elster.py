"""Availability boundary for the official SDK; never simulate a successful filing.

ERiC is obtained through the reviewed developer registration, not PyPI:
https://www.elster.de/elsterweb/infoseite/entwickler
The actual year-specific XML mapping and native bridge must be built and tested
against the licensed SDK headers/schema after access is available.
"""
import os
from pathlib import Path


def status():
    sdk = Path(os.environ.get("BUCHHALTUNG_ERIC_DIR", "/opt/buchhaltung/private/eric"))
    certificate = os.environ.get("BUCHHALTUNG_ELSTER_CERT", "")
    present = any(sdk.glob("**/libericapi.so")) if sdk.is_dir() else False
    manufacturer = bool(os.environ.get("BUCHHALTUNG_ELSTER_MANUFACTURER_ID"))
    return {"state": "integration_pending" if present else "sdk_missing", "can_send": False,
            "sdk_present": present, "certificate_present": bool(certificate and Path(certificate).is_file()),
            "manufacturer_id_present": manufacturer,
            "message": "Envío directo pendiente: requiere ERiC oficial, Hersteller-ID, certificado y validación de la integración con los esquemas del año.",
            "registration_url": "https://www.elster.de/elsterweb/registrierung-entwickler/form",
            "source_url": "https://www.elster.de/elsterweb/infoseite/entwickler"}


def submit(*args, **kwargs):
    raise ValueError("No se ha enviado nada a ELSTER. La integración ERiC todavía no está habilitada.")
