"""Synthetic tests; no credentials, production data or network calls."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from buchhaltung.config import Config
from buchhaltung.db import Database, canonical
from buchhaltung.documents import Documents
from buchhaltung.ledger import Ledger
from buchhaltung.models import RecordInput
from buchhaltung.reports import eur, vat
from buchhaltung.sevdesk import Importer


class SourceFixture:
    def __init__(self, income=False, shared=False):
        self.income, self.shared = income, shared
        self.centre, self.log_id, self.amount = None, "1", "100"
        self.tax_rule, self.comment = "1", "QA Leistung"

    def object(self, sid="1"):
        return {"id": sid, "voucherDate": "2026-09-01", "description": "QA Beleg " + sid,
                "supplierName": "QA Supplier", "costCentre": self.centre if sid == "1" else {"id": "1"},
                "creditDebit": "D" if self.income else "C", "status": "1000", "currency": "EUR",
                "sumGross": self.amount, "sumNet": self.amount, "sumTax": "0", "paidAmount": self.amount,
                "taxRule": {"id": "15" if self.income else self.tax_rule}, "document": {"id": sid}}

    def list(self, model, params=None):
        data = {"StaticCountry": [{"id": "1", "code": "DE"}],
                "CostCentre": [{"id": "1", "name": "Ingenieur Freiberufler"}, {"id": "2", "name": "Gewerbe Software"}],
                "SevClient": [{"id": "1", "defaultCurrency": "EUR"}],
                "CheckAccount": [{"id": "1", "name": "QA Bank", "currency": "EUR"}],
                "CheckAccountTransaction": [{"id": "1", "entryDate": "2026-09-01", "amount": "200" if self.income and self.shared else "100" if self.income else "-200" if self.shared else "-100", "checkAccount": {"id": "1"}, "status": "400"}],
                "Voucher": [self.object()] + ([self.object("2")] if self.shared else [])}
        if model == "VoucherPos":
            sid = str(params["voucher[id]"])
            return [{"id": sid, "comment": self.comment, "sumNetAccounting": self.amount,
                     "sumTaxAccounting": "0", "taxRate": "0", "isAsset": "0"}]
        return copy.deepcopy(data.get(model, []))

    def get(self, path, params=None):
        sid = path.split("/")[1]
        if path.endswith("getCheckAccountTransactionLogs"):
            return {"objects": [{"id": self.log_id if sid == "1" else "other", "amountPaid": self.amount if self.income else "-" + self.amount,
                                  "bookingDate": "2026-09-01", "checkAccountTransaction": {"id": "1"},
                                  "object": {"id": sid}, "fromStatus": "100", "toStatus": "400"}]}
        if path.endswith("getCheckAccountTransactions"):
            return {"objects": self.list("CheckAccountTransaction")}
        if path.endswith("download"):
            return {"objects": {"base64Encoded": True, "content": base64.b64encode(b"%PDF-1.4\nQA original " + sid.encode()).decode(), "filename": "qa.pdf"}}
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

    def run_import(self, fixture, approved=False):
        return Importer(self.config, self.db, self.docs, self.ledger, fixture,
                        {"sevdesk/Voucher/1": "1"} if approved else {}).run(2026)

    def test_authorized_centre_rebooking_preserves_cash_ids_and_retries(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        with self.db.connect() as db:
            original_payment = dict(db.execute("SELECT * FROM payments").fetchone())
        source.centre, source.log_id = {"id": "1"}, "new-log"
        refreshed = self.run_import(source, approved=True)
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

    def test_unapproved_and_financial_changes_stay_blocked_on_retries(self):
        source = SourceFixture()
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.centre, source.log_id = {"id": "1"}, "new-log"
        for _ in range(2):
            result = self.run_import(source)
            self.assertEqual(result["state"], "needs_attention")
            self.assertEqual(result["source_drift"], ["sevdesk/Voucher/1"])
        source.amount = "101"
        self.assertEqual(self.run_import(source, approved=True)["state"], "needs_attention")
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payment_source_aliases").fetchone()[0], 0)
        self.assertEqual(self.ledger.get("sev_voucher_1")["total"], 10000)

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

    def test_exact_source_metadata_revision_never_guesses_a_tax_code(self):
        source = SourceFixture()
        source.centre = {"id": "1"}
        self.assertEqual(self.run_import(source)["state"], "complete")
        source.tax_rule, source.comment, source.log_id = "12", "Updated source comment; legal review pending.", "new-log"
        bundle = {"object": source.object(), "positions": source.list("VoucherPos", {"voucher[id]": "1"}),
                  "payment_logs": source.get("Voucher/1/getCheckAccountTransactionLogs")["objects"]}
        digest = hashlib.sha256(canonical(bundle).encode()).hexdigest()
        wrong = Importer(self.config, self.db, self.docs, self.ledger, source, {}, {"sevdesk/Voucher/1": "0" * 64}).run(2026)
        self.assertEqual(wrong["state"], "needs_attention")
        result = Importer(self.config, self.db, self.docs, self.ledger, source, {}, {"sevdesk/Voucher/1": digest}).run(2026)
        self.assertEqual(result["state"], "complete", result)
        self.assertEqual(result["cost_centres_refreshed"], [])
        self.assertEqual(result["source_metadata_refreshed"], ["sevdesk/Voucher/1"])
        record = self.ledger.get("sev_voucher_1")
        self.assertEqual(record["data"]["source_tax_rule"], "12")
        self.assertEqual(record["data"]["lines"][0]["tax_code"], "unclassified")
        self.assertEqual((record["total"], record["paid"]), (10000, 10000))
        self.assertEqual(self.run_import(source)["state"], "complete")


if __name__ == "__main__":
    unittest.main()
