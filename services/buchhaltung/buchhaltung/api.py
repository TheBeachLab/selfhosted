from datetime import date, timedelta
import hashlib
import hmac
import io
import csv
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from . import __version__
from .bank import import_bank
from .config import Config
from .db import Database, canonical, identity, now
from .documents import Documents, MAX_DOCUMENT, media_type
from .elster import status as elster_status, submit as elster_submit
from .invoices import preview_invoice, issue_invoice
from .ledger import Ledger, total
from .models import ACTIVITIES, CATEGORIES, TAX_CODES, StrictModel, Party, RecordInput, PaymentInput, MatchInput, ReviewInput
from .reports import eur, vat, save_return, ledger_fingerprint


class SettingsInput(StrictModel):
    seller: Party
    vat_method: Literal["ist", "soll", "unconfirmed"]
    number_prefix: str = Field(pattern=r"^[A-Za-z0-9_{}.-]{1,35}$")
    next_number: int = Field(ge=1, le=999999999)
    fiscal_reviewed: bool


class RevisionInput(StrictModel):
    revision: int = Field(ge=1)


class ClassificationInput(StrictModel):
    classification: Literal["private", "transfer", "excluded", "unreviewed"]
    reason: str = Field(min_length=4, max_length=1000)


class BankAccountInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ReturnInput(StrictModel):
    type: Literal["eur", "ustva"]
    period: str = Field(pattern=r"^20\d\d(-\d\d)?$")
    activity: Literal["freiberufler", "gewerbe"] | None = None


class AnnualCloseInput(ReviewInput):
    notes: str = Field(min_length=10, max_length=3000)


def create_app(config=None):
    config = config or Config.environment()
    database = Database(config.data)
    documents = Documents(config, database)
    ledger = Ledger(database, documents)
    app = FastAPI(title="Beach Lab Buchhaltung", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config, app.state.database, app.state.documents, app.state.ledger = config, database, documents, ledger

    @app.middleware("http")
    async def protection(request, call_next):
        username = request.headers.get("x-authentik-username", "")
        secret = request.headers.get("x-buchhaltung-proxy", "")
        if username != config.owner or not hmac.compare_digest(secret, config.proxy_secret):
            return JSONResponse({"detail": "Acceso reservado a Fran con passkey."}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") != config.origin or request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
                return JSONResponse({"detail": "Origen no autorizado."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(KeyError)
    async def key_error(request, error):
        return JSONResponse({"detail": str(error.args[0])}, status_code=404)

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, error):
        return JSONResponse({"detail": "El registro ya existe o está cerrado; recarga antes de continuar."}, status_code=409)

    @app.get("/healthz")
    def health():
        with database.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"state": "ok", "version": __version__}

    @app.get("/api/bootstrap")
    def bootstrap():
        with database.connect() as db:
            last = db.execute("SELECT * FROM imports ORDER BY started DESC LIMIT 1").fetchone()
            importer = dict(last) if last else {"state": "scheduled", **database.setting("import_schedule", db)}
            if last:
                importer["summary"] = json.loads(importer["summary"])
            contacts = [{"id": row["id"], **json.loads(row["data"])} for row in db.execute("SELECT * FROM contacts ORDER BY id")]
            accounts = [dict(row) for row in db.execute("SELECT * FROM bank_accounts ORDER BY name")]
        return {"owner": "Fran", "activities": ACTIVITIES, "tax_codes": TAX_CODES, "categories": CATEGORIES,
                "settings": database.setting(), "import": importer, "elster": elster_status(), "contacts": contacts,
                "accounts": accounts, "version": __version__}

    @app.put("/api/settings")
    def settings(payload: SettingsInput):
        if payload.fiscal_reviewed:
            if payload.vat_method == "unconfirmed" or not payload.seller.tax_number:
                raise ValueError("Confirma el método fiscal y la Steuernummer antes de guardar como verificado.")
            if not all(getattr(payload.seller, name) for name in ("name", "street", "city", "postcode", "email")):
                raise ValueError("Completa la identidad del emisor.")
        if "{" in payload.number_prefix.replace("{year}", "") or "}" in payload.number_prefix.replace("{year}", ""):
            raise ValueError("Solo se admite {year} como variable de numeración.")
        with database.transaction() as db:
            current = database.setting(db=db)
            if payload.next_number < current["next_number"]:
                raise ValueError("La secuencia de facturas no puede retroceder.")
            value = payload.model_dump(mode="json")
            database.set_setting(db, "settings", value)
            database.audit(db, "settings.updated", "settings", value)
        return value

    @app.post("/api/contacts", status_code=201)
    def create_contact(payload: Party):
        contact_id = identity("contact")
        with database.transaction() as db:
            db.execute("INSERT INTO contacts(id,data) VALUES(?,?)", (contact_id, canonical(payload.model_dump(mode="json"))))
            database.audit(db, "contact.created", contact_id, payload.model_dump(mode="json"))
        return {"id": contact_id, **payload.model_dump(mode="json")}

    @app.put("/api/contacts/{contact_id}")
    def edit_contact(contact_id: str, payload: Party):
        with database.transaction() as db:
            if not db.execute("UPDATE contacts SET data=? WHERE id=?", (canonical(payload.model_dump(mode="json")), contact_id)).rowcount:
                raise KeyError("Cliente no encontrado.")
            database.audit(db, "contact.updated", contact_id, payload.model_dump(mode="json"))
        return {"id": contact_id, **payload.model_dump(mode="json")}

    @app.get("/api/records")
    def records(kind: str | None = None, start: date = date(2026, 10, 1), end: date = date(2026, 12, 31)):
        if kind not in (None, "expenses", "invoice", "income", "asset", "expense"):
            raise ValueError("Tipo no válido.")
        return ledger.list(kind, str(start), str(end))

    @app.get("/api/records/{record_id}")
    def get_record(record_id: str):
        value = ledger.get(record_id)
        with database.connect() as db:
            value["payments"] = [dict(row) for row in db.execute("SELECT * FROM payments WHERE record_id=? ORDER BY date", (record_id,))]
        return value

    @app.post("/api/records", status_code=201)
    def create_record(payload: RecordInput):
        return ledger.save(payload)

    @app.put("/api/records/{record_id}")
    def edit_record(record_id: str, payload: RecordInput):
        return ledger.save(payload, record_id)

    @app.post("/api/records/{record_id}/review")
    def review_record(record_id: str, payload: RevisionInput):
        return ledger.review(record_id, payload.revision)

    @app.post("/api/records/{record_id}/void")
    def void_draft(record_id: str, payload: RevisionInput):
        with database.transaction() as db:
            value = ledger.get(record_id, db)
            if value["state"] != "draft" or value["source"] or value["revision"] != payload.revision:
                raise ValueError("Solo puedes descartar un borrador nuevo sin emisión.")
            db.execute("UPDATE records SET state='void',updated=? WHERE id=?", (now(), record_id))
            database.audit(db, "draft.voided", record_id, {"revision": payload.revision})
        return {"state": "void"}

    @app.get("/api/records/{record_id}/invoice-preview")
    def preview(record_id: str):
        return preview_invoice(config, database, ledger, record_id)

    @app.post("/api/records/{record_id}/issue")
    def issue(record_id: str, payload: ReviewInput):
        return issue_invoice(config, database, documents, ledger, record_id, payload.sha256)

    @app.post("/api/records/{record_id}/payments")
    def record_payment(record_id: str, payload: PaymentInput):
        return {"id": ledger.payment(record_id, payload)}

    @app.post("/api/payments/{payment_id}/reverse")
    def reverse_payment(payment_id: str):
        return {"id": ledger.reverse_payment(payment_id)}

    @app.post("/api/documents", status_code=201)
    async def upload(file: UploadFile = File(...)):
        raw = await file.read(MAX_DOCUMENT + 1)
        media = media_type(raw)
        with database.transaction() as db:
            doc_id = documents.store(db, raw, file.filename or "justificante", media)
        return {"id": doc_id, "filename": Path(file.filename or "justificante").name, "media_type": media}

    @app.get("/api/documents/{document_id}")
    def download(document_id: str):
        metadata, data = documents.read(document_id)
        filename = quote(metadata["filename"], safe="")
        return Response(data, media_type=metadata["media_type"], headers={"Content-Disposition": "attachment; filename*=UTF-8''" + filename})

    @app.get("/api/bank")
    def bank(start: date = date(2026, 10, 1), end: date = date(2026, 12, 31)):
        with database.connect() as db:
            return [dict(row) for row in db.execute("SELECT b.id,b.account_id,b.date,b.amount,b.purpose,b.party,b.reference,b.classification,a.name AS account, (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.bank_id=b.id AND reversed_by IS NULL) AS matched FROM bank_transactions b JOIN bank_accounts a ON a.id=b.account_id WHERE b.date BETWEEN ? AND ? ORDER BY b.date DESC,b.id LIMIT 20000", (str(start), str(end)))]

    @app.post("/api/bank/accounts", status_code=201)
    def create_account(payload: BankAccountInput):
        account_id = identity("account")
        with database.transaction() as db:
            db.execute("INSERT INTO bank_accounts(id,name,currency) VALUES(?,?,'EUR')", (account_id, payload.name))
            database.audit(db, "bank_account.created", account_id, {"name": payload.name})
        return {"id": account_id, "name": payload.name, "currency": "EUR"}

    @app.post("/api/bank/import")
    async def import_statement(account_id: str = Form(...), file: UploadFile = File(...)):
        raw = await file.read(MAX_DOCUMENT + 1)
        return import_bank(database, documents, account_id, raw, file.filename or "extracto")

    @app.post("/api/bank/{bank_id}/match")
    def match(bank_id: str, payload: MatchInput):
        with database.transaction() as db:
            movement = db.execute("SELECT date FROM bank_transactions WHERE id=?", (bank_id,)).fetchone()
            if not movement:
                raise KeyError("Movimiento no encontrado.")
            payment = PaymentInput(bank_id=bank_id, date=movement["date"], amount=payload.amount)
            result = ledger.payment(payload.record_id, payment, db=db)
        return {"payment": result}

    @app.post("/api/bank/{bank_id}/classify")
    def classify(bank_id: str, payload: ClassificationInput):
        with database.transaction() as db:
            movement = db.execute("SELECT amount FROM bank_transactions WHERE id=?", (bank_id,)).fetchone()
            if not movement:
                raise KeyError("Movimiento no encontrado.")
            used = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE bank_id=? AND reversed_by IS NULL", (bank_id,)).fetchone()[0]
            remaining = abs(movement["amount"]) - used
            if used and not remaining and payload.classification != "unreviewed":
                raise ValueError("El movimiento ya está completamente conciliado. Revierte el pago si necesitas corregirlo.")
            if not db.execute("UPDATE bank_transactions SET classification=? WHERE id=?", (payload.classification, bank_id)).rowcount:
                raise KeyError("Movimiento no encontrado.")
            database.audit(db, "bank.classified", bank_id, {**payload.model_dump(mode="json"), "unmatched_cents": remaining, "business_matched_cents": used})
        return {"state": payload.classification}

    @app.get("/api/reports/eur/{year}")
    def eur_report(year: int):
        if not 2026 <= year <= 2099:
            raise ValueError("Año no válido.")
        return eur(database, year)

    @app.get("/api/reports/vat/{period}")
    def vat_report(period: str):
        if not re.fullmatch(r"20\d\d-\d\d", period):
            raise ValueError("Periodo no válido.")
        return vat(database, period)

    @app.post("/api/reports/eur/{year}/close")
    def annual_close(year: int, payload: AnnualCloseInput):
        if not 2026 <= year <= 2099 or date.today() < date(year+1,1,1):
            raise ValueError("Solo se puede confirmar el cierre de un ejercicio terminado.")
        with database.transaction() as db:
            current = ledger_fingerprint(db)
            if current != payload.sha256:
                raise ValueError("Los datos cambiaron desde la revisión anual. Vuelve a revisar.")
            database.set_setting(db, "year_reviewed_" + str(year), current)
            database.audit(db, "year.closed_review", str(year), {"sha256": current, "notes": payload.notes})
        return eur(database, year)

    @app.get("/api/elster/registration-draft")
    def registration_draft():
        seller = database.setting().get("seller") or {}
        if not seller.get("name") or not seller.get("email"):
            raise ValueError("Completa la identidad y email del emisor antes de preparar la solicitud.")
        return {"destination": "Bayerisches Landesamt für Steuern · ELSTER Entwicklerregistrierung",
                "url": "https://www.elster.de/elsterweb/registrierung-entwickler/form", "sent": False,
                "name": seller["name"], "company": seller["name"], "email": seller["email"],
                "phone": seller.get("phone", ""), "website": "https://beachlab.org",
                "reason": "Ich entwickle eine ausschließlich selbst genutzte, selbst gehostete Buchhaltungsanwendung für meine freiberufliche Ingenieurtätigkeit und mein Softwaregewerbe. Ich möchte ERiC zur Plausibilisierung und authentifizierten Übermittlung monatlicher Umsatzsteuer-Voranmeldungen sowie getrennter jährlicher Einnahmenüberschussrechnungen integrieren. Es erfolgt kein Vertrieb an Dritte. Ich bitte um Zugang zum Entwicklerbereich und Informationen zur Beantragung der Hersteller-ID."}

    @app.post("/api/returns/prepare", status_code=201)
    def prepare_return(payload: ReturnInput):
        if payload.type == "eur":
            if not payload.activity or "-" in payload.period:
                raise ValueError("Indica año y actividad para una EÜR separada.")
            report = eur(database, int(payload.period))
            report["activities"] = [item for item in report["activities"] if item["activity"] == payload.activity]
            report["activity"] = payload.activity
        else:
            if "-" not in payload.period:
                raise ValueError("Indica el mes de UStVA.")
            report = vat(database, payload.period)
        return save_return(database, report)

    @app.post("/api/returns/{return_id}/send")
    def send_return(return_id: str, payload: ReviewInput):
        with database.connect() as db:
            row = db.execute("SELECT * FROM returns WHERE id=?", (return_id,)).fetchone()
            if not row or row["sha256"] != payload.sha256 or row["state"] != "prepared":
                raise ValueError("La declaración no coincide con la vista revisada.")
        return elster_submit(row, payload)

    @app.get("/api/returns")
    def list_returns():
        with database.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,type,period,activity,sha256,state,created,receipt_document FROM returns ORDER BY created DESC")]

    @app.get("/api/exports/eur/{year}/{activity}")
    def export_eur(year: int, activity: Literal["freiberufler", "gewerbe"]):
        report = eur_report(year)
        item = next(item for item in report["activities"] if item["activity"] == activity)
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["EÜR", year, item["name"], "Borrador" if not report["ready"] else "Preparada; no enviada"])
        writer.writerow(["Concepto", "EUR"])
        for key, value in item["values"].items():
            writer.writerow([key, format(value / 100, ".2f")])
        writer.writerow(["Revisión pendiente"])
        for issue in report["blockers"]:
            writer.writerow(["'" + issue])
        return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="EUR-{year}-{activity}.csv"'})

    @app.get("/api/exports/vat/{period}")
    def export_vat(period: str):
        return Response(canonical(vat_report(period)), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="USTVA-{period}-review.json"'})

    @app.get("/api/audit")
    def audit():
        verified = database.verify_audit()
        with database.connect() as db:
            events = [dict(row) for row in db.execute("SELECT seq,at,actor,event,entity,sha256 FROM audit ORDER BY seq DESC LIMIT 200")]
        return {"verification": verified, "events": events}

    if (config.dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=config.dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def shell(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "Ruta no encontrada.")
        index = config.dist / "index.html"
        if not index.is_file():
            raise HTTPException(503, "Interfaz pendiente de compilación.")
        return FileResponse(index)

    return app


def app_factory():
    return create_app()
