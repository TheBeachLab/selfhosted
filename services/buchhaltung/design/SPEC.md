# Buchhaltung: implementation specification

Requested on 2026-10-12: a small private accounting application on the NUC,
`buchhaltung.beachlab.org`, with passkey access for Fran, used from Q4 2026.
The workflows take inspiration from sevdesk; no sevdesk assets or code are copied.

## Accepted design references

`expenses-desktop.png` and `invoice-mobile.png` were generated with the built-in
Imagegen tool before implementation. They are references, not background images.
The desktop reference governs the shell and empty expenses page; the mobile
reference governs the new-invoice form. OS status bars are not part of the app.

Prompt: a restrained German bookkeeping application, Spanish UI, white background,
slate text, thin gray borders, orange primary actions, narrow left navigation,
inspired by sevdesk's invoice/expense workflow; no imaginary transactions, totals,
charts or compliance badges. Desktop: expenses table and PDF/XML/image upload.
Mobile: new invoice form, activity selection, dates, concept, base, VAT and total.

## Tokens and component families

| Token | Value |
| --- | --- |
| Canvas / surfaces | #ffffff |
| Primary text | #26313e |
| Secondary text | #66717c |
| Border | #e4e7eb |
| Action / selection | #ee5b35 |
| Selection tint | #fff4ee |
| Font | system sans-serif; no third-party font requests |
| Radius | 5px controls, 0px page sections |
| Desktop sidebar | 220px at 1440px viewport |
| Main padding | 48px desktop; 24px tablet; 20px mobile |
| Controls | 44px minimum; 14px body, 32px page headings |

Families: page shell, section toolbar, form fields, flat data table, empty state,
upload band, inline validation message, contextual details sheet, report table.
Use outline SVG icons, no decorative photography, gradients or card grid.
At 760px the sidebar becomes an accessible menu, tables scroll horizontally, and
forms collapse to one column except the date and amount pairs.

## Copy and page inventory

Shell: Beach Lab / Buchhaltung; Facturas, Gastos, Banco, EÜR, IVA, Configuración.
Period `2026 · T4`, account `Fran`. Default page: Gastos.

Expenses: `Gastos`, `Nuevo gasto`, `Actividad`, `Todas`, `Periodo`, `T4 2026`;
columns `Fecha`, `Proveedor`, `Actividad`, `Base`, `IVA`, `Total`, `Estado`.
Empty state: `Todavía no hay gastos.` / `Añade un justificante para empezar.`
Upload: `Arrastra un PDF, XML o imagen` / `Seleccionar archivo`.
Import footer reads the actual stored schedule/status; it must not stay
"programada" after a successful, failed or overdue import.

Invoices: list, contacts, draft editor, review, validated XML/PDF download.
Draft: `Nueva factura`, `Cliente`, `Actividad`, `Fecha`, `Vencimiento`, `Concepto`,
`Base (€)`, `IVA`, `Total`, `Guardar borrador`. Use today's date, not the
illustrative date in the reference. Multiple line items use the same field family.

Bank: CSV/CAMT import, account selection, original transactions, reconciliation
with an invoice/expense, explicit partial amounts and cash payment dates.
EÜR: two annual statements, cash basis, activity allocation and export.
IVA: monthly combined UStVA, tax fields, blockers, saved review snapshot.
Settings: issuer identity, tax cash/accrual method, numbering, contacts, ELSTER
requirements and import status. Do not label a local JSON export as an ELSTER file.

## Behavior and evidence

No client-side secrets or financial data in browser storage. All persistent data
and original documents stay on the NUC. No demonstration entries in production.
The app must refuse missing fiscal classifications, missing originals or duplicate
reconciliation. Reports are provisional until the relevant blockers are resolved.
No actual invoice, tax return or email is issued/sent during implementation QA.

Functional QA uses a separate temporary database and synthetic identities.
Visual QA must compare native-size reference and screenshots at desktop and mobile,
record at least five fidelity checks and an above-the-fold copy diff in QA.md.
