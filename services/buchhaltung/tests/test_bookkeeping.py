from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from buchhaltung.api import create_app
from buchhaltung.bank import import_bank
from buchhaltung.config import Config
from buchhaltung.cli import backup, restore
from buchhaltung.db import canonical
from buchhaltung.invoices import ubl, validate_xml
from buchhaltung.models import RecordInput, PaymentInput, apportion
from buchhaltung.reports import eur, vat, save_return, ledger_fingerprint
from buchhaltung.sevdesk import Importer, ReadOnlyClient, SourceError

ROOT = Path(__file__).resolve().parents[1]
SELLER = dict(name="QA Engineering", street="Teststrasse 1", postcode="10115", city="Berlin", country="DE",
              email="test@example.org", phone="+49 30 1234567", vat_id="DE123456789", tax_number="123/456/78901",
              iban="DE89370400440532013000", buyer_reference="")
BUYER = {**SELLER, "name": "QA Buyer", "email": "buyer@example.org", "buyer_reference": "TEST-001"}


class BookkeepingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(Path(self.temp.name), "http://127.0.0.1:8765", "test-only-" + "x"*40, b"t"*32,
                             dist=ROOT / "frontend/dist", validator=ROOT / "vendor/xrechnung")
        self.app = create_app(self.config)
        self.db, self.docs, self.ledger = self.app.state.database, self.app.state.documents, self.app.state.ledger
        self.client = TestClient(self.app, headers={"X-Authentik-Username": "fran", "X-Buchhaltung-Proxy": self.config.proxy_secret,
                                                  "Origin": self.config.origin, "Sec-Fetch-Site": "same-origin"})
        with self.db.transaction() as db:
            self.db.set_setting(db, "settings", {"seller": SELLER, "vat_method": "ist", "number_prefix": "QA-{year}-", "next_number": 1, "fiscal_reviewed": True})
            self.db.set_setting(db, "import_schedule", {"at": "2000-01-01T20:00:00+02:00", "year": 2026})
        self.contact = self.client.post("/api/contacts", json=BUYER).json()["id"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def record(self, kind="expense", activity="freiberufler", net=10000, tax=1900, code="de19", date_value="2026-09-01", state="reviewed"):
        payload = RecordInput(kind=kind, date=date_value, due_date=date_value if kind=="invoice" else None,
                              service_date=date_value, party_id=self.contact if kind=="invoice" else None, party_name="QA Supplier",
                              lines=[dict(description="QA Leistung", activity=activity, net_cents=net, tax_cents=tax,
                                          tax_code=code, category="software", deduct_percent=100)])
        record = self.ledger.save(payload)
        with self.db.transaction() as db:
            db.execute("UPDATE records SET state=? WHERE id=?", (state, record["id"]))
        return self.ledger.get(record["id"])

    def test_auth_owner_secret_and_origin(self):
        unauth = TestClient(self.app)
        self.assertEqual(unauth.get("/api/bootstrap").status_code, 403)
        self.assertEqual(unauth.get("/", headers={"X-Authentik-Username":"fran"}).status_code,403)
        self.assertEqual(self.client.get("/api/bootstrap", headers={"X-Authentik-Username":"fran-jr"}).status_code,403)
        self.assertEqual(self.client.post("/api/contacts",json=BUYER,headers={"Origin":"https://evil.example"}).status_code,403)
        self.assertEqual(self.client.post("/api/contacts",json=BUYER,headers={"Sec-Fetch-Site":"same-site"}).status_code,403)
        self.assertEqual(self.client.get("/api/bootstrap").status_code,200)
        self.assertIn("no-store",self.client.get("/").headers["cache-control"])

    def test_document_encryption_integrity_and_audit_append_only(self):
        raw=b"%PDF-1.4\nsynthetic test document"
        with self.db.transaction() as db:
            doc=self.docs.store(db,raw,"qa.pdf","application/pdf")
            self.assertEqual(self.docs.store(db,raw,"again.pdf","application/pdf"),doc)
        meta,reopened=self.docs.read(doc)
        self.assertEqual(reopened,raw)
        encrypted=(self.config.data/"documents"/(meta["sha256"]+".enc")).read_bytes()
        self.assertNotIn(raw,encrypted)
        self.assertGreater(self.db.verify_audit()["events"],0)
        with self.assertRaises(sqlite3.IntegrityError), self.db.transaction() as db:
            db.execute("DELETE FROM audit")
        (self.config.data/"documents"/(meta["sha256"]+".enc")).write_bytes(encrypted[:-1]+bytes([encrypted[-1]^1]))
        with self.assertRaises(Exception):
            self.docs.read(doc)

    def test_partial_bank_match_duplicate_and_reversal(self):
        record=self.record()
        account=self.client.post("/api/bank/accounts",json={"name":"QA Bank"}).json()["id"]
        csv=b"date;amount;party;purpose;reference\n2026-09-01;-59,50;QA Supplier;QA;ref1\n"
        self.assertEqual(import_bank(self.db,self.docs,account,csv,"qa.csv")["added"],1)
        self.assertEqual(import_bank(self.db,self.docs,account,csv,"qa.csv")["added"],0)
        movement=self.client.get("/api/bank?start=2026-01-01&end=2026-12-31").json()[0]
        match=self.client.post("/api/bank/"+movement["id"]+"/match",json={"record_id":record["id"],"amount":5950})
        self.assertEqual(match.status_code,200,match.text)
        again=self.client.post("/api/bank/"+movement["id"]+"/match",json={"record_id":record["id"],"amount":5950})
        self.assertEqual(again.status_code,422)
        self.assertEqual(self.ledger.get(record["id"])["paid"],5950)
        self.assertEqual(self.client.post("/api/payments/"+match.json()["payment"]+"/reverse").status_code,200)
        self.assertEqual(self.ledger.get(record["id"])["paid"],0)

    def test_eur_cash_basis_separate_activities_and_vat_cash(self):
        invoice=self.record(kind="invoice",state="issued")
        expense=self.record(net=2000,tax=380)
        trade=self.record(kind="invoice",activity="gewerbe",net=5000,tax=950,state="issued")
        paid=self.record(kind="tax_payment",net=570,tax=0,code="none")
        self.ledger.payment(invoice["id"],PaymentInput(date="2026-09-01",amount=5950))
        self.ledger.payment(expense["id"],PaymentInput(date="2026-09-01",amount=2380))
        self.ledger.payment(trade["id"],PaymentInput(date="2026-09-01",amount=5950))
        self.ledger.payment(paid["id"],PaymentInput(date="2026-09-01",amount=570))
        report=eur(self.db,2026)
        activities={x["activity"]:x["values"] for x in report["activities"]}
        self.assertEqual(activities["freiberufler"]["revenue_net"],5000)
        self.assertEqual(activities["freiberufler"]["vat_received"],950)
        self.assertEqual(activities["freiberufler"]["input_vat_paid"],380)
        self.assertEqual(activities["freiberufler"]["profit"],3000)
        self.assertEqual(activities["gewerbe"]["profit"],5950)

    def test_shared_bank_payment_private_remainder_preserves_business_match(self):
        record=self.record()
        account=self.client.post('/api/bank/accounts',json={'name':'Shared QA'}).json()['id']
        import_bank(self.db,self.docs,account,b'date;amount\n2026-09-01;-119,00\n','shared.csv')
        movement=self.client.get('/api/bank?start=2026-01-01&end=2026-12-31').json()[0]
        self.assertEqual(self.client.post('/api/bank/'+movement['id']+'/match',json={'record_id':record['id'],'amount':5950}).status_code,200)
        classified=self.client.post('/api/bank/'+movement['id']+'/classify',json={'classification':'private','reason':'Private passenger; business half separately verified.'})
        self.assertEqual(classified.status_code,200,classified.text)
        self.assertEqual(self.ledger.get(record['id'])['paid'],5950)
        self.assertEqual(self.client.post('/api/bank/'+movement['id']+'/match',json={'record_id':record['id'],'amount':5950}).status_code,422)
        self.assertFalse(any('movimientos bancarios' in item for item in eur(self.db,2026)['blockers']))

    def test_vat_ist_soll_reverse_charge_and_eu_performance(self):
        invoice=self.record(kind="invoice",state="issued")
        self.ledger.payment(invoice["id"],PaymentInput(date="2026-09-01",amount=5950))
        self.record(net=2000,tax=380)
        self.record(net=1000,tax=0,code="rc_expense_eu")
        self.record(net=2000,tax=0,code="rc_expense_other")
        self.record(kind="invoice",activity="gewerbe",net=5000,tax=0,code="rc_income_eu",state="issued")
        self.record(kind="invoice",net=1000,tax=0,code="de0",state="issued")
        report=vat(self.db,"2026-09")
        self.assertEqual(report["fields"]["81"],"50")
        self.assertEqual(report["fields"]["46"],"10")
        self.assertEqual(report["fields"]["47"],"1.9")
        self.assertEqual(report["fields"]["85"],"3.8")
        self.assertEqual(report["fields"]["67"],"5.7")
        self.assertEqual(report["fields"]["21"],"50")
        self.assertEqual(report["payable_cents"],570)
        with self.db.transaction() as db:
            settings=self.db.setting(db=db);settings["vat_method"]="soll";self.db.set_setting(db,"settings",settings)
        self.assertEqual(vat(self.db,"2026-09")["fields"]["81"],"100")
        self.assertEqual(vat(self.db,"2026-09")["fields"]["87"],"10")

    def test_soll_advance_not_double_counted(self):
        invoice=self.record(kind="invoice",date_value="2026-09-01",state="issued")
        self.ledger.payment(invoice["id"],PaymentInput(date="2026-08-01",amount=5950))
        with self.db.transaction() as db:
            settings=self.db.setting(db=db);settings["vat_method"]="soll";self.db.set_setting(db,"settings",settings)
        self.assertEqual(vat(self.db,"2026-08")["fields"]["81"],"50")
        self.assertEqual(vat(self.db,"2026-09")["fields"]["81"],"50")

    def test_rounding_over_many_partial_payments(self):
        invoice=self.record(kind="invoice",net=100,tax=19,state="issued")
        for i in range(119):
            self.ledger.payment(invoice["id"],PaymentInput(date="2026-09-01",amount=1))
        values=eur(self.db,2026)["activities"][0]["values"]
        self.assertEqual(values["revenue_net"],100)
        self.assertEqual(values["vat_received"],19)
        self.assertEqual(sum(apportion(119,[59,60])),119)

    def test_invoice_validation_number_lock_and_pdf_xml(self):
        if not (self.config.validator/"validator.jar").is_file():
            self.skipTest("Official validator missing; install it before deployment.")
        record=self.record(kind="invoice",state="draft")
        preview=self.client.get("/api/records/"+record["id"]+"/invoice-preview")
        self.assertEqual(preview.status_code,200,preview.text)
        invalid=self.client.post("/api/records/"+record["id"]+"/issue",json={"sha256":"0"*64,"confirm":True})
        self.assertEqual(invalid.status_code,422)
        self.assertEqual(self.db.setting()["next_number"],1)
        issued=self.client.post("/api/records/"+record["id"]+"/issue",json={"sha256":preview.json()["sha256"],"confirm":True})
        self.assertEqual(issued.status_code,200,issued.text)
        self.assertEqual(issued.json()["number"],"QA-2026-0001")
        self.assertEqual({d["role"] for d in issued.json()["documents"]},{"invoice_pdf","invoice_xml","validation"})
        self.assertEqual(self.db.setting()["next_number"],2)
        with self.assertRaises(sqlite3.IntegrityError), self.db.transaction() as db:
            db.execute("UPDATE records SET data='{}' WHERE id=?",(record["id"],))
        data=record["data"]
        broken=ubl('QA-broken',data,SELLER,BUYER).replace(b'>19.00<',b'>18.00<',1)
        with self.assertRaises(ValueError):
            validate_xml(self.config,broken)

    def test_annual_declarations_separate_and_no_fake_elster_submission(self):
        for activity in ("freiberufler","gewerbe"):
            report={"ready":True,"type":"eur","period":"2026","activity":activity,"activities":[{"activity":activity}],"blockers":[]}
            prepared=save_return(self.db,report)
            response=self.client.post('/api/returns/'+prepared["id"]+'/send',json={"sha256":prepared["sha256"],"confirm":True})
            self.assertEqual(response.status_code,422)
            self.assertIn('No se ha enviado',response.json()["detail"])
        with self.db.connect() as db:
            self.assertEqual([x[0] for x in db.execute("SELECT activity FROM returns ORDER BY activity")],["freiberufler","gewerbe"])
        self.assertFalse(self.client.get('/api/bootstrap').json()["elster"]["can_send"])

    def test_readonly_client_rejects_nonwhitelisted_routes(self):
        client=ReadOnlyClient('test-only-key')
        try:
            for path in ('https://evil.example','Voucher/Factory/saveVoucher','Invoice/1/sendViaEmail','../Contact','Invoice/1/bookAmount'):
                with self.assertRaises(SourceError):client.get(path)
        finally:client.close()

    def test_encrypted_backup_actual_isolated_restore(self):
        record=self.record()
        with self.db.transaction() as db:self.docs.store(db,b'%PDF-1.4\nbackup original','backup.pdf','application/pdf',record['id'])
        archive=Path(self.temp.name)/'test.blenc'
        result=backup(self.config,self.db,self.docs,archive)
        self.assertTrue(result['verified'])
        self.assertEqual(result['restore']['records'],1)
        self.assertEqual(result['restore']['documents'],1)
        opened=restore(self.config,archive,Path(self.temp.name)/'separate-recovery')
        self.assertEqual(opened['audit'],self.db.verify_audit())
        with self.assertRaises(ValueError):restore(self.config,archive,self.config.data)
        raw=archive.read_bytes();archive.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaises(Exception):restore(self.config,archive,Path(self.temp.name)/'tampered-recovery')

    def test_import_time_guard_and_resume_idempotency(self):
        raw_pdf=b"%PDF-1.4\nfixture-original"
        class FakeClient:
            def list(inner,model,params=None):
                data={"StaticCountry":[{"id":"1","code":"DE"}],"CostCentre":[{"id":"1","name":"Ingenieur Freiberufler"}],
                      "SevClient":[{"id":"1","defaultCurrency":"EUR"}],"Contact":[{"id":"1","name":"QA Buyer"}],"ContactAddress":[],"CommunicationWay":[],
                      "CheckAccount":[{"id":"1","name":"QA Bank","currency":"EUR"}],
                      "CheckAccountTransaction":[{"id":"1","entryDate":"2026-09-01","amount":"119","checkAccount":{"id":"1"},"status":"400"}],
                      "Invoice":[{"id":"1","invoiceDate":"2026-09-01","invoiceNumber":"SOURCE-1","contact":{"id":"1"},"costCentre":{"id":"1"},"taxRule":{"id":"1"},"status":"1000","sumGross":"119","sumNet":"100","sumTax":"19","paidAmount":"119","invoiceType":"RE"}],
                      "InvoicePos":[{"id":"1","name":"QA Leistung","sumNetAccounting":"100","sumTaxAccounting":"19","taxRate":"19"}],"Voucher":[],"CreditNote":[]}
                return data.get(model,[])
            def get(inner,path,params=None):
                import base64
                if path.endswith('getCheckAccountTransactionLogs'):
                    return {"objects":[{"id":"1","checkAccountTransaction":{"id":"1"},"bookingDate":"2026-09-01","amountPaid":"119"}]}
                if path.endswith('getCheckAccountTransactions'):
                    return {"objects":inner.list('CheckAccountTransaction')}
                if path.endswith('getPdf'):
                    return {"objects":{"base64Encoded":True,"content":base64.b64encode(raw_pdf).decode(),"filename":"SOURCE-1.pdf"}}
                if path.endswith('getXml'):
                    return {"objects":"<?xml version='1.0'?><Original/>"}
                raise AssertionError(path)
        importer=lambda:Importer(self.config,self.db,self.docs,self.ledger,FakeClient())
        with self.db.transaction() as db:self.db.set_setting(db,'import_schedule',{"at":"2099-01-01T20:00:00+02:00"})
        with self.assertRaises(SourceError):importer().run(2026)
        with self.db.transaction() as db:self.db.set_setting(db,'import_schedule',{"at":"2000-01-01T20:00:00+02:00"})
        first=importer().run(2026)
        self.assertEqual(first['state'],'complete',first)
        with self.db.connect() as db:counts=[db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('records','payments','documents','source_revisions')]
        second=importer().run(2026)
        self.assertEqual(second['state'],'complete',second)
        with self.db.connect() as db:self.assertEqual(counts,[db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('records','payments','documents','source_revisions')])
        self.assertEqual(self.ledger.get('sev_invoice_1')['paid'],11900)


if __name__ == '__main__':
    unittest.main()
