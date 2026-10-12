from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from zoneinfo import ZoneInfo

from .db import canonical, identity, now
from .models import ACTIVITIES, apportion, tax_for

# Field mapping checked against the BMF USt 1 A 2026 official form (2025-12-29).
# https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/2025-12-29-vordruckmuster-USt-voranmeldung-2026.pdf
VAT_FIELDS = {"81": "Umsätze zu 19 % · Bemessungsgrundlage", "86": "Umsätze zu 7 % · Bemessungsgrundlage",
              "46": "EU-Dienstleistungen § 13b · Bemessungsgrundlage", "47": "EU-Dienstleistungen § 13b · Steuer",
              "84": "Andere Leistungen § 13b · Bemessungsgrundlage", "85": "Andere Leistungen § 13b · Steuer",
              "66": "Vorsteuer aus inländischen Rechnungen", "67": "Vorsteuer aus § 13b",
              "21": "Dienstleistungen EU, nicht in DE steuerbar", "45": "Andere nicht steuerbare Umsätze",
              "60": "Umsätze § 13b, Leistungsempfänger schuldet Steuer", "48": "Steuerfreie Umsätze ohne Vorsteuerabzug",
              "87": "Umsätze zu 0 % · Bemessungsgrundlage"}
BASE_FIELDS = {"81", "86", "46", "84", "21", "45", "60", "48", "87"}


def month_range(period):
    first = date.fromisoformat(period + "-01")
    following = date(first.year + (first.month == 12), 1 if first.month == 12 else first.month + 1, 1)
    return first.isoformat(), following.isoformat()


def blockers(database, db, start, end, annual=False):
    issues = []
    settings = database.setting(db=db)
    if not settings.get("fiscal_reviewed"):
        issues.append("Confirma la configuración fiscal en Configuración.")
    last = db.execute("SELECT * FROM imports WHERE year=? ORDER BY started DESC LIMIT 1", (int(start[:4]),)).fetchone()
    if not last or last["state"] != "complete":
        issues.append("Falta importar y verificar el histórico de sevdesk de este año.")
    if database.setting("source_drift", db):
        issues.append("La última copia de sevdesk tiene discrepancias pendientes de verificar.")
    rows = db.execute("SELECT id,kind,state,data FROM records WHERE date>=? AND date<? AND state NOT IN ('void','cancelled','private')", (start, end)).fetchall()
    for row in rows:
        if row["state"] not in ("issued", "reviewed"):
            issues.append(f"{row['id']}: documento pendiente de revisión o emisión.")
        data = json.loads(row["data"])
        if any(line.get("tax_code") == "unclassified" or line.get("category") == "unclassified" or line.get("activity") not in ACTIVITIES for line in data["lines"]):
            issues.append(f"{row['id']}: clasificación fiscal o actividad pendiente.")
        if data.get("source_unsupported"):
            issues.append(f"{row['id']}: {data['source_unsupported']}")
        if data.get("source_sync_error"):
            issues.append(f"{row['id']}: {data['source_sync_error']}")
    unresolved = db.execute("SELECT COUNT(*) FROM bank_transactions b WHERE b.date>=? AND b.date<? AND classification='unreviewed' AND ABS(amount)>(SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.bank_id=b.id AND reversed_by IS NULL)", (start, end)).fetchone()[0]
    if unresolved:
        issues.append(f"{unresolved} movimientos bancarios pendientes de conciliación o clasificación.")
    # Payments from another issue year still require a reviewed source document.
    for row in db.execute("SELECT DISTINCT r.id FROM payments p JOIN records r ON r.id=p.record_id WHERE p.date>=? AND p.date<? AND p.reversed_by IS NULL AND r.state NOT IN ('issued','reviewed','private')", (start, end)):
        issues.append(f"{row['id']}: pago de un documento sin revisión.")
    close = database.setting("year_reviewed_" + start[:4], db)
    if annual and close != ledger_fingerprint(db):
        issues.append("Confirma el cierre anual: activos iniciales, gastos pendientes y regla de diez días (§ 11 EStG).")
    return sorted(set(issues))


def eur(database, year):
    start, end = f"{year}-01-01", f"{year+1}-01-01"
    summaries = {activity: defaultdict(int) for activity in ACTIVITIES}
    evidence = {activity: [] for activity in ACTIVITIES}
    with database.connect() as db:
        issues = blockers(database, db, start, end, annual=True)
        if datetime.now(ZoneInfo("Europe/Berlin")).date() < date(year+1,1,1):
            issues.append("El ejercicio todavía no ha terminado; la EÜR sigue siendo un borrador.")
        rows = db.execute("SELECT p.*,r.kind,r.state,r.data FROM payments p JOIN records r ON r.id=p.record_id WHERE p.date>=? AND p.date<? AND p.reversed_by IS NULL AND r.state IN ('issued','reviewed') ORDER BY p.date,p.id", (start, end)).fetchall()
        for row in rows:
            data = json.loads(row["data"])
            weights = [line["net_cents"] + line["tax_cents"] for line in data["lines"]]
            before = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL AND (date<? OR (date=? AND id<?))", (row["record_id"],row["date"],row["date"],row["id"])).fetchone()[0]
            previous = apportion(before, weights)
            after = apportion(before+row["amount"],weights)
            portions = [a-b for a,b in zip(after,previous)]
            for i,(line, portion) in enumerate(zip(data["lines"], portions)):
                activity = line["activity"]
                if activity not in summaries:
                    continue
                summary = summaries[activity]
                gross = line["net_cents"] + line["tax_cents"]
                # Derive cash VAT from gross, not a separately rounded net share.
                tax = ((after[i] * line["tax_cents"] + gross // 2) // gross - (previous[i] * line["tax_cents"] + gross // 2) // gross) if gross else 0
                net = portion - tax
                if row["kind"] == "tax_refund" or line["category"] == "vat_refund":
                    summary["vat_refunds"] += portion
                elif row["kind"] == "tax_payment" or line["category"] == "vat_payment":
                    summary["vat_paid"] += portion
                elif row["kind"] in ("invoice", "income"):
                    summary["revenue_net"] += net
                    summary["vat_received"] += tax
                else:
                    deductible = (portion * line.get("deduct_percent", 100) + 50) // 100
                    deductible_tax = (tax * line.get("deduct_percent", 100) + 50) // 100 if line["tax_code"] in ("de19", "de7") else 0
                    summary["input_vat_paid"] += deductible_tax
                    if row["kind"] != "asset":
                        amount = deductible - deductible_tax
                        summary["expenses"] += amount
                        summary["category_" + line["category"]] += amount
                evidence[activity].append({"record": row["record_id"], "payment": row["id"], "date": row["date"], "gross_cents": portion})
        for row in db.execute("SELECT id,data FROM records WHERE kind='asset' AND state='reviewed'"):
            data = json.loads(row["data"])
            asset_start = date.fromisoformat(data["asset_start"])
            life = data["asset_life_months"]
            offset = (year - asset_start.year) * 12 - asset_start.month + 1
            months = max(0, min(life, offset + 12) - max(0, offset))
            for line in data["lines"]:
                tax_deductible = line["tax_cents"] if line["tax_code"] in ("de19", "de7") else 0
                cost = (line["net_cents"] + line["tax_cents"] - tax_deductible) * line.get("deduct_percent", 100) // 100
                # Cumulative rounding avoids losing cents across multiple years.
                before = max(0, min(life, offset))
                after = max(0, min(life, offset + 12))
                depreciation = (cost * after + life // 2) // life - (cost * before + life // 2) // life
                summaries[line["activity"]]["depreciation"] += depreciation
        output = []
        for activity, values in summaries.items():
            values["income_total"] = values["revenue_net"] + values["vat_received"] + values["vat_refunds"]
            values["expense_total"] = values["expenses"] + values["input_vat_paid"] + values["vat_paid"] + values["depreciation"]
            values["profit"] = values["income_total"] - values["expense_total"]
            output.append({"activity": activity, "name": ACTIVITIES[activity], "values": dict(values), "evidence": evidence[activity]})
    with database.connect() as db:
        fingerprint = ledger_fingerprint(db)
    return {"type": "eur", "period": str(year), "activities": output, "blockers": issues, "ready": not issues, "fingerprint": fingerprint,
            "basis": "Zufluss/Abfluss; IVA cobrado/pagado incluido. Revisión anual pendiente antes de enviar."}


def vat(database, period):
    start, end = month_range(period)
    fields = defaultdict(int)
    evidence = []
    with database.connect() as db:
        settings = database.setting(db=db)
        issues = blockers(database, db, start, end)
        if datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat() < end:
            issues.append("El mes todavía no ha terminado; la UStVA sigue siendo un borrador.")
        method = settings.get("vat_method")
        if method not in ("ist", "soll"):
            issues.append("Confirma Ist-Versteuerung o Soll-Versteuerung con tu configuración fiscal.")
        for row in db.execute("SELECT * FROM records WHERE state IN ('issued','reviewed') AND kind NOT IN ('tax_payment','tax_refund')"):
            data = json.loads(row["data"])
            income = row["kind"] in ("invoice", "income")
            effective = []
            service_date = data.get("service_date") or row["date"]
            weights = [line["net_cents"] + line["tax_cents"] for line in data["lines"]]
            if not sum(weights):
                issues.append(f"{row['id']}: total cero o conversión pendiente.")
                continue
            # Domestic Ist follows cash. EU non-taxable service reporting follows
            # performance even under Ist; §18b UStG, official USt 1 E 2026.
            before_cash = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL AND date<?", (row["id"],start)).fetchone()[0]
            month_cash = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL AND date>=? AND date<?", (row["id"],start,end)).fetchone()[0]
            before_parts, after_parts = apportion(before_cash,weights), apportion(before_cash+month_cash,weights)
            advance = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL AND date<?", (row["id"],service_date)).fetchone()[0]
            advances = apportion(advance,weights)
            for i,line in enumerate(data["lines"]):
                gross = weights[i]
                if not gross:
                    continue
                domestic = line["tax_code"] in ("de19","de7","de0")
                if income and domestic and method == "ist":
                    net = ((after_parts[i]*line["net_cents"]+gross//2)//gross - (before_parts[i]*line["net_cents"]+gross//2)//gross)
                    if net:
                        effective.append((line,net,after_parts[i]-before_parts[i]))
                elif income and domestic and method == "soll":
                    if start <= service_date < end:
                        # Remaining value at performance plus any advances in this
                        # same period; previous advances were already declared.
                        prior = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL AND date<? AND date<?", (row["id"],start,service_date)).fetchone()[0]
                        prior_parts = apportion(prior,weights)
                        net = line["net_cents"] - (prior_parts[i]*line["net_cents"]+gross//2)//gross
                        effective.append((line,net,gross-prior_parts[i]))
                    elif service_date >= end and month_cash:
                        net = ((after_parts[i]*line["net_cents"]+gross//2)//gross - (before_parts[i]*line["net_cents"]+gross//2)//gross)
                        effective.append((line,net,after_parts[i]-before_parts[i]))
                else:
                    # For ordinary German input VAT, use receipt/invoice date.
                    # Reverse charge service tax point uses the supplied service date.
                    point = service_date if income or line["tax_code"].startswith("rc_expense") else row["date"]
                    if start <= point < end:
                        effective.append((line,line["net_cents"],gross))
            for line, net, gross in effective:
                code = line["tax_code"]
                if income:
                    field = {"de19": "81", "de7": "86", "de0": "87", "rc_income_eu": "21", "rc_income_other": "45", "rc_income_de": "60", "exempt": "48"}.get(code)
                    if field:
                        fields[field] += net
                    else:
                        issues.append(f"{row['id']}: tratamiento de ingreso no soportado para UStVA.")
                elif code in ("de19", "de7"):
                    fields["66"] += (line["tax_cents"] * line.get("deduct_percent", 100) + 50) // 100
                elif code in ("rc_expense_eu", "rc_expense_other"):
                    base_field, tax_field = ("46", "47") if code == "rc_expense_eu" else ("84", "85")
                    tax = tax_for(net, 19)
                    fields[base_field] += net
                    fields[tax_field] += tax
                    fields["67"] += (tax * line.get("deduct_percent", 100) + 50) // 100
                elif code not in ("foreign", "none", "de0", "exempt"):
                    issues.append(f"{row['id']}: tratamiento de gasto no soportado para UStVA.")
                evidence.append({"record": row["id"], "code": code, "base_cents": net, "gross_cents": gross, "activity": line["activity"]})
        # Bases on the official form are whole euros; taxes retain cents.
        values = {field: str(Decimal(fields[field]) / 100) if field not in BASE_FIELDS else str(fields[field] // 100) for field in VAT_FIELDS}
        payable = tax_for((fields["81"] // 100) * 100, 19) + tax_for((fields["86"] // 100) * 100, 7) + fields["47"] + fields["85"] - fields["66"] - fields["67"]
    issues = sorted(set(issues))
    return {"type": "ustva", "period": period, "vat_method": method, "fields": values,
            "labels": VAT_FIELDS, "payable_cents": payable, "evidence": evidence, "blockers": issues,
            "ready": not issues, "basis": "Ambas actividades del mismo empresario; no incluye casos fiscales sin clasificar."}


def ledger_fingerprint(db):
    state = [[list(row) for row in db.execute(query)] for query in (
        "SELECT id,revision,state,data FROM records ORDER BY id",
        "SELECT id,record_id,date,amount,reversed_by FROM payments ORDER BY id",
        "SELECT id,date,amount,classification FROM bank_transactions ORDER BY id",
        "SELECT key,value FROM meta WHERE key='settings' ORDER BY key")]
    return hashlib.sha256(canonical(state).encode()).hexdigest()


def save_return(database, report):
    if not report["ready"]:
        raise ValueError("Resuelve los avisos de revisión antes de guardar la declaración.")
    body = canonical(report)
    digest = hashlib.sha256(body.encode()).hexdigest()
    return_id = identity("return")
    with database.transaction() as db:
        db.execute("INSERT INTO returns(id,type,period,activity,snapshot,sha256,state,created) VALUES(?,?,?,?,?,?,'prepared',?)",
                   (return_id, report["type"], report["period"], report.get("activity"), body, digest, now()))
        database.audit(db, "return.prepared", return_id, {"sha256": digest, "period": report["period"], "type": report["type"]})
    return {"id": return_id, "sha256": digest, "state": "prepared", "elster_sent": False}
