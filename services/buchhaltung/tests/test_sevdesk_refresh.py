"""Synthetic tests; no credentials, production data or network calls."""
import base64
import copy
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest

from buchhaltung.config import Config
from buchhaltung.db import Database, canonical
from buchhaltung.documents import Documents
from buchhaltung.ledger import Ledger
from buchhaltung.models import RecordInput, PaymentInput
from buchhaltung.reports import eur, vat
from buchhaltung.sevdesk import Importer


class SourceFixture:
    def __init__(self, income=False, shared=False):
        self.income, self.shared = income, shared
        self.centre, self.log_id, self.amount = None, "1", "100"
        self.tax_rule, self.comment = "1", "QA Leistung"
        self.date, self.bank_amount, self.paid, self.pdf = "2026-09-01", None, None, b"QA original"
        self.deleted, self.logs_override = False, None
        self.bank_date, self.value_date = None, None

    def object(self, sid="1"):
        return {"id": sid, "voucherDate": self.date, "description": "QA Beleg " + sid,
                "supplierName": "QA Supplier", "costCentre": self.centre if sid == "1" else {"id": "1"},
                "creditDebit": "D" if self.income else "C", "status": "1000", "currency": "EUR",
                "sumGross": self.amount, "sumNet": self.amount, "sumTax": "0", "paidAmount": self.amount if self.paid is None else self.paid,
                "taxRule": {"id": "15" if self.income else self.tax_rule}, "document": {"id": sid}}

    def list(self, model, params=None):
        data = {"StaticCountry": [{"id": "1", "code": "DE"}],
                "CostCentre": [{"id": "1", "name": "Ingenieur Freiberufler"}, {"id": "2", "name": "Gewerbe Software"}],
                "SevClient": [{"id": "1", "defaultCurrency": "EUR"}],
                "CheckAccount": [{"id": "1", "name": "QA Bank", "currency": "EUR"}],
                "CheckAccountTransaction": [{"id": "1", "entryDate": self.bank_date or self.date, "valueDate": self.value_date or self.date, "amount": self.bank_amount or (("" if self.income else "-") + ("200" if self.shared else self.amount)), "checkAccount": {"id": "1"}, "status": "400"}],
                "Voucher": [] if self.deleted else [self.object()] + ([self.object("2")] if self.shared else [])}
        if model == "VoucherPos":
            sid = str(params["voucher[id]"])
            return [{"id": sid, "comment": self.comment, "sumNetAccounting": self.amount,
                     "sumTaxAccounting": "0", "taxRate": "0", "isAsset": "0"}]
        return copy.deepcopy(data.get(model, []))

    def get(self, path, params=None):
        sid = path.split("/")[1]
        if path.endswith("getCheckAccountTransactionLogs"):
            if self.logs_override is not None:
                return {"objects": copy.deepcopy(self.logs_override)}
            if self.paid == "0":
                return {"objects": []}
            return {"objects": [{"id": self.log_id if sid == "1" else "other", "amountPaid": self.amount if self.income else "-" + self.amount,
                                  "bookingDate": self.date, "checkAccountTransaction": {"id": "1"},
                                  "object": {"id": sid}, "fromStatus": "100", "toStatus": "400"}]}
        if path.endswith("getCheckAccountTransactions"):
            return {"objects": self.list("CheckAccountTransaction")}
        if path.endswith("download"):
            return {"objects": {"base64Encoded": True, "content": base64.b64encode(b"%PDF-1.4\n" + self.pdf + sid.encode()).decode(), "filename": "qa.pdf"}}
        if path.startswith("Document/"):
            return {"objects": [{"id": sid, "filename": "qa.pdf"}]}
        raise AssertionError(path)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(Path(self.temp.name), "http://127.0.0.1:8765", "test-only-" + "x" * 40, b"t" * 32)
        self.db = Database(self.config.data)
        self.docs = Documents(self.config, self.db)
        self.ledger = Ledger(self.db, self.docs)
        with self.db.transaction() as db:
            self.db.set_setting(db, "import_schedule", {"at": "2000-01-01T20:00:00+02:00"})

    def tearDown(self):
        self.temp.cleanup()

    def run_import(self, fixture):
        return Importer(self.config, self.db, self.docs, self.ledger, fixture).run(2026)

    def test_automatic_centre_rebooking_preserves_cash_ids_and_retries(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        with self.db.connect() as db:
            original_payment = dict(db.execute("SELECT * FROM payments").fetchone())
        source.centre, source.log_id = {"id": "1"}, "new-log"
        refreshed = self.run_import(source)
        self.assertEqual(refreshed["state"], "complete", refreshed)
        with self.db.connect() as db:
            self.assertEqual(original_payment, dict(db.execute("SELECT * FROM payments").fetchone()))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT payment_id FROM payment_source_aliases").fetchone()[0], original_payment["id"])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM source_revisions WHERE source='sevdesk/Voucher/1'").fetchone()[0], 2)
        current = self.ledger.get("sev_voucher_1")
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["data"]["source_unsupported"], "")
        self.assertEqual(current["data"]["lines"][0]["tax_code"], "unclassified")
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get("sev_voucher_1")["revision"], 2)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)

    def test_latest_financial_revision_replaces_current_amount_date_and_same_log_id(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        with self.db.connect() as db:
            original = dict(db.execute("SELECT * FROM payments").fetchone())
        source.amount, source.date = "80", "2026-10-02"
        result = self.run_import(source)
        self.assertEqual(result["state"], "complete", result)
        current = self.ledger.get("sev_voucher_1")
        self.assertEqual((current["total"], current["paid"], current["reconciled_paid"], current["date"]), (8000, 8000, 8000, source.date))
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments WHERE reversed_by IS NULL").fetchone()[0], 1)
            previous = dict(db.execute("SELECT * FROM payments WHERE id=?", (original["id"],)).fetchone())
            self.assertTrue(previous.pop("reversed_by"))
            original.pop("reversed_by")
            self.assertEqual(previous, original)
            self.assertEqual(db.execute("SELECT payment_id FROM payment_source_current").fetchone()[0], db.execute("SELECT id FROM payments WHERE reversed_by IS NULL").fetchone()[0])
            self.assertEqual(tuple(db.execute("SELECT date,amount FROM bank_transactions").fetchone()), (source.date, -8000))
        revision = current["revision"]
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get(current["id"])["revision"], revision)

    def test_inconsistent_latest_source_never_falls_back_to_old_cash_on_retry(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.amount, source.bank_amount = "101", "-100"
        for _ in range(2):
            result = self.run_import(source)
            self.assertEqual(result["state"], "needs_attention", result)
            current = self.ledger.get("sev_voucher_1")
            self.assertEqual((current["total"], current["paid"], current["reconciled_paid"]), (10100, 10100, 0))
            self.assertTrue(current["data"]["source_sync_error"])
            self.assertEqual(result["source_drift"], ["sevdesk/Voucher/1"])
        self.assertFalse(eur(self.db, 2026)["ready"])

    def test_source_payment_removed_and_restored_is_never_counted_twice(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.paid = "0"
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get("sev_voucher_1")["paid"], 0)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments WHERE reversed_by IS NULL").fetchone()[0], 0)
        source.paid = None
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.run_import(source)["state"], "complete")
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT SUM(amount) FROM payments WHERE reversed_by IS NULL").fetchone()[0], 10000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 2)

    def test_private_part_of_shared_bank_payment_never_enters_eur_or_vat(self):
        source = SourceFixture(shared=True)
        self.assertEqual(self.run_import(source)["state"], "complete")
        private = self.ledger.classify_imported("sev_voucher_1", "private", "Owner confirmed the source private withdrawal.")
        revision = private["revision"]
        self.assertEqual(private["state"], "private")
        self.assertEqual(private["paid"], 10000)
        self.assertEqual(private["data"]["lines"][0]["deduct_percent"], 0)
        self.assertEqual(self.ledger.classify_imported("sev_voucher_1", "private", "Owner confirmed the source private withdrawal.")["revision"], revision)
        business = self.ledger.get("sev_voucher_2")
        payload = {k: v for k, v in business["data"].items() if not k.startswith("source_")}
        payload["lines"][0].update(tax_code="none", category="software")
        payload["revision"] = business["revision"]
        reviewed = self.ledger.save(RecordInput.model_validate(payload), business["id"])
        self.ledger.review(business["id"], reviewed["revision"])
        report = eur(self.db, 2026)
        self.assertEqual(report["activities"][0]["values"]["expenses"], 10000)
        self.assertFalse(any("sev_voucher_1" in issue for issue in report["blockers"]))
        self.assertFalse(any(row["record"] == "sev_voucher_1" for row in vat(self.db, "2026-09")["evidence"]))
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT SUM(amount) FROM payments").fetchone()[0], 20000)
            self.assertEqual(db.execute("SELECT classification FROM bank_transactions").fetchone()[0], "unreviewed")
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get(private["id"])["state"], "private")

    def test_confirmed_tax_refund_keeps_activity_allocation_pending(self):
        source = SourceFixture(income=True)
        self.assertEqual(self.run_import(source)["state"], "complete")
        result = self.ledger.classify_imported("sev_voucher_1", "tax_refund", "Owner and source bank reference confirm a VAT refund.")
        self.assertEqual((result["kind"], result["state"], result["paid"]), ("tax_refund", "needs_review", 10000))
        self.assertEqual(result["data"]["lines"][0]["category"], "vat_refund")
        self.assertTrue(result["data"]["source_activity_pending"])
        with self.assertRaisesRegex(ValueError, "no soportado"):
            self.ledger.review(result["id"], result["revision"])
        self.assertEqual(eur(self.db, 2026)["activities"][0]["values"]["vat_refunds"], 0)

    def test_private_classification_cannot_hide_an_unsupported_asset(self):
        self.assertEqual(self.run_import(SourceFixture())["state"], "complete")
        record = self.ledger.get("sev_voucher_1")
        data = record["data"]
        data["source_unsupported"] = "Activo de sevdesk: falta importar/verificar su cuadro de amortización."
        with self.db.transaction() as db:
            db.execute("UPDATE records SET data=? WHERE id=?", (canonical(data), record["id"]))
        with self.assertRaisesRegex(ValueError, "activos"):
            self.ledger.classify_imported(record["id"], "private", "Synthetic user request requiring further asset review.")
        self.assertEqual(self.ledger.get(record["id"])["state"], "needs_review")

    def test_latest_source_tax_metadata_invalidates_review_without_guessing_tax_code(self):
        source = SourceFixture()
        source.centre = {"id": "1"}
        self.assertEqual(self.run_import(source)["state"], "complete")
        record = self.ledger.get("sev_voucher_1")
        payload = {k: v for k, v in record["data"].items() if not k.startswith("source_")}
        payload["lines"][0].update(tax_code="none", category="software")
        payload["revision"] = record["revision"]
        reviewed = self.ledger.save(RecordInput.model_validate(payload), record["id"])
        self.ledger.review(record["id"], reviewed["revision"])
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get(record["id"])["state"], "reviewed")
        source.tax_rule, source.comment, source.log_id, source.centre = "12", "Updated source comment; legal review pending.", "new-log", {"id": "2"}
        result = self.run_import(source)
        self.assertEqual(result["state"], "complete", result)
        record = self.ledger.get("sev_voucher_1")
        self.assertEqual(record["state"], "needs_review")
        self.assertEqual(record["data"]["source_tax_rule"], "12")
        self.assertEqual(record["data"]["lines"][0]["tax_code"], "unclassified")
        self.assertEqual(record["data"]["lines"][0]["activity"], "gewerbe")
        self.assertEqual((record["total"], record["paid"]), (10000, 10000))
        self.assertEqual(self.run_import(source)["state"], "complete")

    def test_latest_original_is_the_only_document_shown_and_old_bytes_are_audit(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        old = self.ledger.get("sev_voucher_1")["data"]["source_documents"]
        source.pdf = b"CORRECTED source original"
        self.assertEqual(self.run_import(source)["state"], "complete")
        current = self.ledger.get("sev_voucher_1")
        self.assertFalse(set(old) & {doc["id"] for doc in current["documents"]})
        self.assertEqual(len([doc for doc in current["documents"] if doc["role"] == "original"]), 1)
        for doc in old:
            self.assertIn(b"QA original", self.docs.read(doc)[1])
        self.assertIn(b"CORRECTED", self.docs.read(current["data"]["source_documents"][0])[1])

    def test_missing_source_record_is_removed_from_current_lists_and_reappears_once(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.deleted = True
        result = self.run_import(source)
        self.assertEqual(result["state"], "complete", result)
        self.assertEqual(result["source_removed"], ["sevdesk/Voucher/1"])
        self.assertEqual(self.ledger.list(), [])
        self.assertEqual(self.ledger.get("sev_voucher_1")["reconciled_paid"], 0)
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.deleted = False
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(len(self.ledger.list()), 1)
        self.assertEqual(self.ledger.get("sev_voucher_1")["reconciled_paid"], 10000)

    def test_source_payment_date_may_differ_from_bank_entry_date(self):
        source = SourceFixture()
        source.date, source.bank_date, source.value_date = "2026-09-30", "2026-10-02", "2026-09-30"
        result = self.run_import(source)
        self.assertEqual(result["state"], "complete", result)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT date FROM payments WHERE reversed_by IS NULL").fetchone()[0], "2026-09-30")
            bank = db.execute("SELECT * FROM bank_transactions").fetchone()
            self.assertEqual(bank["date"], "2026-10-02")
            self.assertEqual(json.loads(bank["data"])["valueDate"], "2026-09-30")
        self.assertEqual(self.run_import(source)["state"], "complete")
        self.assertEqual(self.ledger.get("sev_voucher_1")["paid"], 10000)

    def test_source_payment_without_booking_date_is_not_guessed_from_bank(self):
        source = SourceFixture()
        log = source.get("Voucher/1/getCheckAccountTransactionLogs")["objects"][0]
        del log["bookingDate"]
        log["create"] = "2026-09-30"
        source.logs_override = [log]
        result = self.run_import(source)
        self.assertEqual(result["state"], "needs_attention", result)
        self.assertEqual(self.ledger.get("sev_voucher_1")["reconciled_paid"], 0)

    def test_original_manual_bank_row_stays_immutable(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        with self.db.transaction() as db:
            db.execute("INSERT INTO bank_transactions(id,account_id,date,amount,purpose,party,reference,data) VALUES('manual','sev_account_1','2026-09-01',-100,'QA','QA','manual','{}')")
        with self.assertRaises(sqlite3.IntegrityError), self.db.transaction() as db:
            db.execute("UPDATE bank_transactions SET amount=-200 WHERE id='manual'")

    def test_duplicate_source_payment_ids_are_an_error_not_extra_cash(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        log = source.get("Voucher/1/getCheckAccountTransactionLogs")["objects"][0]
        source.logs_override = [log, log]
        result = self.run_import(source)
        self.assertEqual(result["state"], "needs_attention", result)
        self.assertEqual(self.ledger.get("sev_voucher_1")["reconciled_paid"], 0)

    def test_imported_financial_fields_and_payments_cannot_be_edited_locally(self):
        source = SourceFixture()
        source.centre = {"id": "1"}
        self.assertEqual(self.run_import(source)["state"], "complete")
        current = self.ledger.get("sev_voucher_1")
        payload = {k: v for k, v in current["data"].items() if not k.startswith("source_")}
        payload["revision"] = current["revision"]
        payload["lines"][0]["net_cents"] += 100
        with self.assertRaisesRegex(ValueError, "sevdesk"):
            self.ledger.save(RecordInput.model_validate(payload), current["id"])
        with self.assertRaisesRegex(ValueError, "sevdesk"):
            self.ledger.payment(current["id"], PaymentInput(date=source.date, amount=1))
        with self.db.connect() as db:
            payment_id = db.execute("SELECT id FROM payments").fetchone()[0]
        with self.assertRaisesRegex(ValueError, "sevdesk"):
            self.ledger.reverse_payment(payment_id)



if __name__ == "__main__":
    unittest.main()
