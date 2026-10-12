from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Activity = Literal["freiberufler", "gewerbe"]
ACTIVITIES = {"freiberufler": "Ingenieur Freiberufler", "gewerbe": "Gewerbe Software"}
TAX_CODES = {
    "de19": "Deutschland 19 %", "de7": "Deutschland 7 %", "de0": "Deutschland 0 %",
    "exempt": "Steuerfrei (§ 4 / § 19, Begründung erforderlich)",
    "rc_income_eu": "Dienstleistung EU, Reverse Charge",
    "rc_income_other": "Dienstleistung Drittland, nicht in DE steuerbar",
    "rc_income_de": "Umsatz § 13b, Leistungsempfänger schuldet Steuer",
    "rc_expense_eu": "Dienstleistung EU, § 13b (19 %)",
    "rc_expense_other": "Dienstleistung Drittland, § 13b (19 %)",
    "foreign": "Ausländische USt, keine deutsche Vorsteuer",
    "none": "Ohne Umsatzsteuer",
    "unclassified": "Pendiente de clasificar",
}
CATEGORIES = {"services": "Fremdleistungen", "software": "Software / Lizenzen", "travel": "Reisekosten",
              "office": "Bürobedarf", "fees": "Gebühren", "other": "Sonstige Betriebsausgaben",
              "asset": "Anlagevermögen", "vat_payment": "Umsatzsteuer an das Finanzamt",
              "vat_refund": "Umsatzsteuererstattung", "unclassified": "Pendiente de clasificar"}


def cents(value):
    try:
        number = Decimal(str(value).replace(",", "."))
        if not number.is_finite() or abs(number) > Decimal("100000000"):
            raise ValueError("Importe fuera de rango.")
        return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError("Importe no válido.") from None


def money(value):
    return format(Decimal(value) / 100, ".2f")


def tax_for(net, rate):
    return int((Decimal(net) * Decimal(str(rate)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def apportion(amount, weights):
    """Largest remainder, stable by line order; exact cents, no float rounding."""
    if amount < 0 or any(weight < 0 for weight in weights) or not sum(weights):
        raise ValueError("No se puede distribuir ese importe.")
    total = sum(weights)
    values = [amount * weight // total for weight in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))
    for i in order[:amount - sum(values)]:
        values[i] += 1
    return values


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Party(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    street: str = Field(default="", max_length=180)
    city: str = Field(default="", max_length=100)
    postcode: str = Field(default="", max_length=20)
    country: str = Field(default="DE", pattern=r"^[A-Z]{2}$")
    email: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=60)
    vat_id: str = Field(default="", max_length=40)
    tax_number: str = Field(default="", max_length=40)
    iban: str = Field(default="", max_length=40)
    buyer_reference: str = Field(default="", max_length=160)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        if value and (value.count("@") != 1 or any(ch.isspace() for ch in value)):
            raise ValueError("Email no válido.")
        return value


class Line(StrictModel):
    description: str = Field(min_length=1, max_length=1000)
    activity: Activity
    net_cents: int = Field(ge=0, le=10_000_000_000)
    tax_cents: int = Field(ge=0, le=10_000_000_000)
    tax_code: str = "de19"
    category: str = "other"
    deduct_percent: int = Field(default=100, ge=0, le=100)

    @model_validator(mode="after")
    def tax_consistency(self):
        if self.tax_code not in TAX_CODES or self.category not in CATEGORIES:
            raise ValueError("Tratamiento fiscal o categoría desconocidos.")
        if self.tax_code in ("de19", "de7", "de0"):
            rate = {"de19": 19, "de7": 7, "de0": 0}[self.tax_code]
            if abs(self.tax_cents - tax_for(self.net_cents, rate)) > 1:
                raise ValueError("El IVA no corresponde a la base y tipo seleccionados.")
        elif self.tax_code not in ("foreign", "unclassified") and self.tax_cents:
            raise ValueError("Este tratamiento no lleva IVA facturado.")
        return self


class RecordInput(StrictModel):
    kind: Literal["invoice", "expense", "income", "tax_payment", "tax_refund", "asset"]
    date: date
    due_date: date | None = None
    service_date: date | None = None
    party_id: str | None = None
    party_name: str = Field(default="", max_length=160)
    reference: str = Field(default="", max_length=180)
    buyer_reference: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=2000)
    exemption_reason: str = Field(default="", max_length=500)
    lines: list[Line] = Field(min_length=1, max_length=100)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    asset_life_months: int | None = Field(default=None, ge=1, le=1200)
    asset_start: date | None = None
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def record_consistency(self):
        if sum(line.net_cents + line.tax_cents for line in self.lines) <= 0:
            raise ValueError("El total debe ser mayor de cero.")
        if self.kind == "invoice":
            if not self.party_id or not self.service_date or not self.due_date:
                raise ValueError("Selecciona cliente, fecha de prestación y vencimiento.")
            if self.due_date < self.date:
                raise ValueError("El vencimiento no puede ser anterior a la factura.")
            if any(line.tax_code.startswith("rc_expense") or line.tax_code in ("foreign", "none") for line in self.lines):
                raise ValueError("Tratamiento fiscal de gasto en una factura de venta.")
            if any(line.deduct_percent != 100 for line in self.lines):
                raise ValueError("Las facturas de venta no admiten porcentaje de deducción.")
        if self.kind in ("expense", "asset") and any(line.tax_code.startswith("rc_income") for line in self.lines):
            raise ValueError("Tratamiento fiscal de ingreso en un gasto.")
        if self.kind in ("tax_payment", "tax_refund") and any(line.tax_code != "none" or line.tax_cents for line in self.lines):
            raise ValueError("El pago/devolución de IVA no lleva IVA adicional.")
        if self.kind == "asset" and (not self.asset_life_months or not self.asset_start):
            raise ValueError("Indica fecha de puesta en uso y vida útil verificada.")
        return self


class PaymentInput(StrictModel):
    bank_id: str | None = None
    date: date
    amount: int = Field(gt=0, le=10_000_000_000)


class MatchInput(StrictModel):
    record_id: str
    amount: int = Field(gt=0, le=10_000_000_000)


class ReviewInput(StrictModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]
