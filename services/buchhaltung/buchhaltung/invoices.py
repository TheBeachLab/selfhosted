from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import io
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .db import canonical, now
from .models import Party, RecordInput, money

NS = {"": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
for prefix, namespace in NS.items():
    ET.register_namespace(prefix, namespace)


def element(parent, name, text=None, **attributes):
    prefix, local = name.split(":")
    node = ET.SubElement(parent, "{" + NS[prefix] + "}" + local, attributes)
    if text is not None:
        node.text = str(text)
    return node


def category(code):
    return {"de19": ("S", 19), "de7": ("S", 7), "de0": ("Z", 0), "exempt": ("E", 0),
            "rc_income_eu": ("AE", 0), "rc_income_de": ("AE", 0)}.get(code)


def check_parties(seller, buyer, data):
    for label, party in (("Emisor", seller), ("Cliente", buyer)):
        for field in ("name", "street", "city", "postcode", "country", "email"):
            if not party.get(field):
                raise ValueError(f"{label}: falta {field} para XRechnung.")
        Party.model_validate(party)
    if not seller.get("phone"):
        raise ValueError("Emisor: falta teléfono de contacto para XRechnung.")
    if not seller.get("iban"):
        raise ValueError("Emisor: falta IBAN para el pago por transferencia.")
    if not seller.get("vat_id") and not seller.get("tax_number"):
        raise ValueError("Emisor: falta USt-IdNr. o Steuernummer.")
    if not (data.get("buyer_reference") or buyer.get("buyer_reference")):
        raise ValueError("Cliente: indica la referencia del comprador (BT-10 / Leitweg-ID si corresponde).")
    if any(category(line["tax_code"]) is None for line in data["lines"]):
        raise ValueError("XRechnung: este caso fiscal todavía no está soportado para emisión.")
    if any(line["tax_code"].startswith("rc_income") for line in data["lines"]) and (not seller.get("vat_id") or not buyer.get("vat_id")):
        raise ValueError("Reverse Charge: falta USt-IdNr. del emisor o cliente.")
    if any(line["tax_code"] == "exempt" for line in data["lines"]) and not data.get("exemption_reason"):
        raise ValueError("Indica el fundamento de la exención.")


def add_party(root, tag, party, seller=False):
    aggregate = element(root, "cac:" + tag)
    node = element(aggregate, "cac:Party")
    element(node, "cbc:EndpointID", party["email"], schemeID="EM")
    name = element(node, "cac:PartyName")
    element(name, "cbc:Name", party["name"])
    address = element(node, "cac:PostalAddress")
    element(address, "cbc:StreetName", party["street"])
    element(address, "cbc:CityName", party["city"])
    element(address, "cbc:PostalZone", party["postcode"])
    country = element(address, "cac:Country")
    element(country, "cbc:IdentificationCode", party["country"])
    if party.get("vat_id"):
        tax = element(node, "cac:PartyTaxScheme")
        element(tax, "cbc:CompanyID", party["vat_id"])
        element(element(tax, "cac:TaxScheme"), "cbc:ID", "VAT")
    if seller and party.get("tax_number"):
        tax = element(node, "cac:PartyTaxScheme")
        element(tax, "cbc:CompanyID", party["tax_number"])
        element(element(tax, "cac:TaxScheme"), "cbc:ID", "FC")
    legal = element(node, "cac:PartyLegalEntity")
    element(legal, "cbc:RegistrationName", party["name"])
    if seller:
        contact = element(node, "cac:Contact")
        element(contact, "cbc:Name", party["name"])
        element(contact, "cbc:Telephone", party["phone"])
        element(contact, "cbc:ElectronicMail", party["email"])


def ubl(number, data, seller, buyer):
    check_parties(seller, buyer, data)
    root = ET.Element("{" + NS[""] + "}Invoice")
    element(root, "cbc:CustomizationID", "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0")
    element(root, "cbc:ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    element(root, "cbc:ID", number)
    element(root, "cbc:IssueDate", data["date"])
    element(root, "cbc:DueDate", data["due_date"])
    element(root, "cbc:InvoiceTypeCode", "380")
    if data.get("note"):
        element(root, "cbc:Note", data["note"])
    element(root, "cbc:DocumentCurrencyCode", "EUR")
    element(root, "cbc:BuyerReference", data.get("buyer_reference") or buyer["buyer_reference"])
    period = element(root, "cac:InvoicePeriod")
    element(period, "cbc:StartDate", data["service_date"])
    element(period, "cbc:EndDate", data["service_date"])
    add_party(root, "AccountingSupplierParty", seller, True)
    add_party(root, "AccountingCustomerParty", buyer)
    payment = element(root, "cac:PaymentMeans")
    element(payment, "cbc:PaymentMeansCode", "58")
    element(payment, "cbc:PaymentID", number)
    account = element(payment, "cac:PayeeFinancialAccount")
    element(account, "cbc:ID", seller["iban"].replace(" ", ""))
    element(account, "cbc:Name", seller["name"])
    terms = element(root, "cac:PaymentTerms")
    element(terms, "cbc:Note", "Zahlbar bis " + data["due_date"] + " unter Angabe der Rechnungsnummer.")
    groups = defaultdict(lambda: [0, 0])
    for line in data["lines"]:
        groups[category(line["tax_code"])][0] += line["net_cents"]
        groups[category(line["tax_code"])][1] += line["tax_cents"]
    net_total = sum(line["net_cents"] for line in data["lines"])
    tax_total = sum(line["tax_cents"] for line in data["lines"])
    tax = element(root, "cac:TaxTotal")
    element(tax, "cbc:TaxAmount", money(tax_total), currencyID="EUR")
    for (code, rate), (net, vat) in groups.items():
        subtotal = element(tax, "cac:TaxSubtotal")
        element(subtotal, "cbc:TaxableAmount", money(net), currencyID="EUR")
        element(subtotal, "cbc:TaxAmount", money(vat), currencyID="EUR")
        cat = element(subtotal, "cac:TaxCategory")
        element(cat, "cbc:ID", code)
        element(cat, "cbc:Percent", rate)
        if code == "AE":
            element(cat, "cbc:TaxExemptionReasonCode", "VATEX-EU-AE")
            element(cat, "cbc:TaxExemptionReason", "Steuerschuldnerschaft des Leistungsempfängers")
        elif code == "E":
            element(cat, "cbc:TaxExemptionReason", data["exemption_reason"])
        element(element(cat, "cac:TaxScheme"), "cbc:ID", "VAT")
    totals = element(root, "cac:LegalMonetaryTotal")
    for name, value in (("LineExtensionAmount", net_total), ("TaxExclusiveAmount", net_total),
                        ("TaxInclusiveAmount", net_total + tax_total), ("PayableAmount", net_total + tax_total)):
        element(totals, "cbc:" + name, money(value), currencyID="EUR")
    for index, line in enumerate(data["lines"], 1):
        node = element(root, "cac:InvoiceLine")
        element(node, "cbc:ID", index)
        element(node, "cbc:InvoicedQuantity", "1", unitCode="C62")
        element(node, "cbc:LineExtensionAmount", money(line["net_cents"]), currencyID="EUR")
        item = element(node, "cac:Item")
        element(item, "cbc:Name", line["description"])
        cat = element(item, "cac:ClassifiedTaxCategory")
        code, rate = category(line["tax_code"])
        element(cat, "cbc:ID", code)
        element(cat, "cbc:Percent", rate)
        element(element(cat, "cac:TaxScheme"), "cbc:ID", "VAT")
        price = element(node, "cac:Price")
        element(price, "cbc:PriceAmount", money(line["net_cents"]), currencyID="EUR")
        element(price, "cbc:BaseQuantity", "1", unitCode="C62")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_xml(config, xml):
    jar = config.validator / "validator.jar"
    scenario = config.validator / "scenarios.xml"
    if not jar.is_file() or not scenario.is_file():
        raise ValueError("No está instalado el validador oficial de XRechnung. La factura no se ha emitido.")
    with tempfile.TemporaryDirectory(prefix="xrechnung-", dir=config.data) as directory:
        root = Path(directory)
        source = root / "invoice.xml"
        source.write_bytes(xml)
        result = subprocess.run(["java", "-Xmx256m", "-jar", str(jar), "-s", str(scenario),
                                 "-r", str(config.validator), "-o", str(root), str(source)],
                                capture_output=True, timeout=45)
        reports = list(root.glob("*-report.xml"))
        if not reports:
            raise ValueError("El validador no devolvió un informe. No se ha emitido la factura.")
        report = reports[0].read_bytes()
        parsed = fromstring(report)
        namespace = "{http://www.xoev.de/de/validator/varl/1}"
        assessment = parsed.find(namespace + "assessment")
        accepted = (parsed.get("valid") == "true" and assessment is not None
                    and assessment.find(namespace + "accept") is not None
                    and assessment.find(namespace + "reject") is None)
        if result.returncode or not accepted:
            # Avoid returning the Java log or private temp paths to the client.
            errors = []
            for node in parsed.iter():
                if node.tag.endswith("failed-assert"):
                    errors.append((node.get("id", "") + ": " + " ".join(node.itertext()).strip())[:300])
            raise ValueError("XRechnung no válida: " + ("; ".join(errors[:6]) or "revisa los datos obligatorios."))
        return report


def invoice_pdf(number, data, seller, buyer):
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontSize, normal.leading = 10, 14
    story = [Paragraph(escape(seller["name"]), styles["Title"]),
             Paragraph(escape(seller["street"] + " · " + seller["postcode"] + " " + seller["city"]), normal),
             Spacer(1, 12 * mm)]
    for value in (buyer["name"], buyer["street"], buyer["postcode"] + " " + buyer["city"], buyer["country"]):
        story.append(Paragraph(escape(value), normal))
    story += [Spacer(1, 10 * mm), Paragraph("Rechnung " + escape(number), styles["Heading1"])]
    for label, value in (("Rechnungsdatum", data["date"]), ("Leistungsdatum", data["service_date"]), ("Zahlbar bis", data["due_date"]),
                         ("Käuferreferenz", data.get("buyer_reference") or buyer.get("buyer_reference", ""))):
        story.append(Paragraph(escape(label + ": " + value), normal))
    story.append(Spacer(1, 7 * mm))
    rows = [["Leistung", "Netto EUR", "USt EUR", "Brutto EUR"]]
    for line in data["lines"]:
        rows.append([Paragraph(escape(line["description"]).replace("\n", "<br/>"), normal),
                     money(line["net_cents"]), money(line["tax_cents"]), money(line["net_cents"] + line["tax_cents"])])
    net = sum(line["net_cents"] for line in data["lines"])
    vat = sum(line["tax_cents"] for line in data["lines"])
    rows.append(["Gesamt", money(net), money(vat), money(net + vat)])
    table = Table(rows, colWidths=[86 * mm, 27 * mm, 27 * mm, 29 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#e4e7eb")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [table, Spacer(1, 8 * mm)]
    if any(line["tax_code"].startswith("rc_income") for line in data["lines"]):
        story.append(Paragraph("Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG).", normal))
    if data.get("exemption_reason"):
        story.append(Paragraph(escape(data["exemption_reason"]), normal))
    if data.get("note"):
        story.append(Paragraph(escape(data["note"]).replace("\n", "<br/>"), normal))
    for text in ("IBAN: " + seller["iban"], "Verwendungszweck: " + number,
                 "USt-IdNr.: " + seller.get("vat_id", ""), "Steuernummer: " + seller.get("tax_number", ""),
                 seller["email"] + " · " + seller["phone"]):
        story.append(Paragraph(escape(text), normal))
    SimpleDocTemplate(output, pagesize=(210 * mm, 297 * mm), leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=20 * mm, title="Rechnung " + number, author=seller["name"]).build(story)
    return output.getvalue()


def invoice_snapshot(database, ledger, record_id, db):
    record = ledger.get(record_id, db)
    if record["state"] != "draft" or record["kind"] != "invoice" or record["source"]:
        raise ValueError("Solo se pueden emitir borradores nuevos.")
    data = RecordInput.model_validate(record["data"]).model_dump(mode="json", exclude={"revision", "document_ids"})
    settings = database.setting(db=db)
    if not settings.get("fiscal_reviewed"):
        raise ValueError("Confirma primero los datos del emisor en Configuración.")
    contact = db.execute("SELECT data FROM contacts WHERE id=?", (data["party_id"],)).fetchone()
    if not contact:
        raise ValueError("Cliente no encontrado.")
    buyer = json.loads(contact[0])
    number = settings["number_prefix"].replace("{year}", data["date"][:4]) + str(settings["next_number"]).zfill(4)
    if db.execute("SELECT 1 FROM records WHERE kind='invoice' AND number=?", (number,)).fetchone():
        raise ValueError("Número ya usado. Revisa la secuencia en Configuración.")
    snapshot = {"number": number, "data": data, "seller": settings["seller"], "buyer": buyer,
                "record_id": record_id, "revision": record["revision"]}
    return snapshot, hashlib.sha256(canonical(snapshot).encode()).hexdigest()


def preview_invoice(config, database, ledger, record_id):
    with database.connect() as db:
        snapshot, digest = invoice_snapshot(database, ledger, record_id, db)
    xml = ubl(snapshot["number"], snapshot["data"], snapshot["seller"], snapshot["buyer"])
    validate_xml(config, xml)
    return {"snapshot": snapshot, "sha256": digest, "validated": True,
            "validator": "KoSIT XRechnung 3.0.2 · 2026-08-31", "issued": False}


def issue_invoice(config, database, documents, ledger, record_id, expected_hash):
    with database.transaction() as db:
        snapshot, digest = invoice_snapshot(database, ledger, record_id, db)
        if digest != expected_hash:
            raise ValueError("La vista revisada cambió. Revisa la factura de nuevo antes de emitir.")
        number, data = snapshot["number"], snapshot["data"]
        xml = ubl(number, data, snapshot["seller"], snapshot["buyer"])
        validation = validate_xml(config, xml)
        pdf = invoice_pdf(number, data, snapshot["seller"], snapshot["buyer"])
        documents.store(db, xml, number + ".xml", "application/xml", record_id, "invoice_xml")
        documents.store(db, pdf, number + ".pdf", "application/pdf", record_id, "invoice_pdf")
        documents.store(db, validation, number + "-validation.xml", "application/xml", record_id, "validation")
        data["seller_snapshot"] = snapshot["seller"]
        data["buyer_snapshot"] = snapshot["buyer"]
        db.execute("UPDATE records SET number=?,data=?,state='issued',updated=? WHERE id=?", (number, canonical(data), now(), record_id))
        settings = database.setting(db=db)
        settings["next_number"] += 1
        database.set_setting(db, "settings", settings)
        database.audit(db, "invoice.issued", record_id, {"number": number, "sha256": digest})
        return ledger.get(record_id, db)
