# Jewelry Repair System

ERP for a jewelry repair and production workshop, built as a set of custom modules on **Odoo 17 Community**.

It covers the whole flow of a B2B repair order: intake, production operations on a planning board, delivery to the client, period billing and invoicing — plus metal accounting by alloy and storage, client metal accounts, a client portal, Telegram notifications and QR labels for a thermal printer.

This repository is a cleaned-up copy of a system running in production, published as a portfolio piece. Business data, deployment configuration and a few client-specific modules are not included.

[Deutsche Version unten](#deutsch)

## Modules

| Module | Purpose |
|--------|---------|
| `jewelry_repair_base` | Repair order, services, production operations, executors, master UI |
| `jewelry_repair_delivery` | Delivery documents (physical hand-over to the client) |
| `jewelry_repair_billing` | Period billing batches → standard Odoo invoices |
| `jewelry_metal_accounting` | Metal accounting by alloy and storage, metal movement documents, losses |
| `jewelry_client_metal_accounts` | Client metal accounts (metal balance per client) |
| `jewelry_stone_orders` | Stone orders to suppliers: request, shipment, receipt, return, transfer into a repair order |
| `jewelry_repair_label` | Order labels with QR code for a narrow thermal printer (TSPL) |
| `jewelry_repair_portal` | Client portal: orders and their status |
| `jewelry_client_metal_portal` | Client metal account on the portal, metal offset against order amounts |
| `jewelry_telegram_notify` | Telegram notifications on order events |
| `jewelry_3d_library` | 3D model library, production order templates |
| `jewelry_expenses` | Expenses: quick expense entry, expense accounts, vendor bills, P&L |
| `jewelry_admin_tools` | Admin tools: bulk record processing, AI-assisted field translation |

Dependency graph:

```
jewelry_repair_base
├── jewelry_repair_delivery
│   └── jewelry_repair_billing
│       ├── jewelry_repair_portal ───────────┐
│       └── jewelry_client_metal_accounts ───┴── jewelry_client_metal_portal
├── jewelry_metal_accounting ── jewelry_client_metal_accounts
├── jewelry_stone_orders
├── jewelry_repair_label
├── jewelry_telegram_notify
├── jewelry_3d_library
└── jewelry_expenses   (+ delivery, billing, account)

jewelry_admin_tools    (base only)
```

## Domain model: separations that are kept strict

Most of the design effort went into keeping concepts apart that look similar but behave differently.

```
Service (service.line)   ≠  Operation (order.operation)
  commercial: goes to the invoice   production: what masters actually do

ready (all operations done)  ≠  delivered (handed over)  ≠  billed (in a billing batch)

delivery (physical hand-over)  ≠  billing (selecting delivered orders for a period)  ≠  invoice (standard Odoo account.move)

client materials (informational)  ≠  workshop materials (stock, invoiced)

executor_id (planned)  ≠  assigned_user_id (actual)
```

Business rules enforced in code and covered by tests:

- An order is an item type / batch; `quantity` may be greater than 1.
- Operations are generated **automatically** from services, aggregated by type and ordered by `sequence`.
- `Start` is available only after `Accept Item` — the master has physically received the piece.
- Only the first unfinished operation of the route can be started.
- After `done`, the piece stays with the current master until the next one accepts it.
- Dragging a card on the planning board assigns the actual executor; `Auto Assign` never overwrites an existing assignment.
- Only delivered orders are billed, and never twice.

### Metal accounting

Metal is tracked per **alloy** (e.g. 585 / 750 gold, 925 silver) and converted to fine metal by **purity**. Every movement — issue to a master, return, casting, scrap, loss — is a document posted between **storages** (main storage, masters, client accounts). Processing losses are recorded explicitly, so a physical inventory can be reconciled against the book balance. Client metal accounts hold metal the client has deposited and offset it against metal used in their orders.

## Tech stack

- Odoo 17 Community, Python 3, PostgreSQL 17
- OWL components and QWeb reports for custom UI and print forms
- Docker Compose for local development
- Anthropic API (optional) for parsing gem certificates and for AI-assisted translation in admin tools
- Telegram Bot API for notifications
- TSPL for thermal label printers
- English source strings, Russian translations in `i18n/ru.po` of each module

## Running locally

```bash
docker compose up -d --build
```

Open http://localhost:8069, create a database and install `jewelry_repair_base` (and any other modules) from Apps. The local stack uses throwaway credentials (`odoo` / `odoo`) — do not reuse them anywhere else.

Optional demo data (users, executors, services and orders in every state, prefixed with `[DEMO]`):

```bash
docker compose exec -T web odoo shell -d <db_name> --db_host=db -r odoo -w odoo < scripts/seed_demo_data.py
```

## Tests

```bash
./scripts/run_tests.sh
```

The script creates a throwaway database, installs every module from scratch without demo data and runs the module test suites (about 200 tests). It fails on a broken clean install as well as on a failing test.

## Spec-driven development (OpenSpec)

Features are developed against written specifications in [`openspec/`](openspec/):

```
openspec/
├── specs/      ← source of truth: current behavior of the system, per domain
└── changes/    ← one folder per feature in progress
    └── <feature>/
        ├── proposal.md   ← why and what
        ├── specs/        ← delta spec (ADDED / MODIFIED / REMOVED requirements, GIVEN/WHEN/THEN scenarios)
        └── tasks.md      ← implementation checklist
```

When a change is finished, its delta is merged into `openspec/specs/` and the folder moves to `openspec/changes/archive/`. Earlier, more detailed design documents (print forms, materials, metal rates and accounting, client metal accounts, gem certificates, label printer protocol) are kept in [`docs/specs/`](docs/specs/). Specs and proposals are written in Russian, the working language of the project.

## License

[LGPL-3.0](LICENSE), the same license as the module manifests.

---

<a id="deutsch"></a>

## Deutsch

**Jewelry Repair System** ist ein ERP für eine Schmuckwerkstatt (Reparatur und Fertigung), umgesetzt als Satz eigener Module für **Odoo 17 Community**.

Abgebildet ist der gesamte Ablauf eines B2B-Reparaturauftrags: Annahme, Fertigungsschritte auf einer Planungstafel, Übergabe an den Kunden, periodische Abrechnung und Rechnungsstellung. Dazu kommen Edelmetallbuchhaltung nach Legierung und Lagerort, Metallkonten der Kunden, ein Kundenportal, Telegram-Benachrichtigungen und QR-Etiketten für einen Thermodrucker.

Dieses Repository ist eine bereinigte Kopie eines produktiv genutzten Systems und dient als Portfolio. Geschäftsdaten, Deployment-Konfiguration und einige kundenspezifische Module sind nicht enthalten.

**Zentrale fachliche Trennungen:**

- *Leistung* (kommerziell, geht in die Rechnung) ≠ *Arbeitsgang* (Fertigung, was die Goldschmiede tatsächlich tun). Arbeitsgänge werden automatisch aus den Leistungen erzeugt.
- *fertig* (alle Arbeitsgänge erledigt) ≠ *übergeben* (an den Kunden ausgehändigt) ≠ *abgerechnet* (in einem Abrechnungslauf).
- *Übergabe* ≠ *Abrechnung* ≠ *Rechnung* (Standard-`account.move` von Odoo). Abgerechnet werden nur übergebene Aufträge, und nie doppelt.
- *geplanter* Ausführender ≠ *tatsächlicher* Ausführender.

**Edelmetall:** Bestände werden je Legierung (z. B. Gold 585/750, Silber 925) geführt und über den Feingehalt in Feinmetall umgerechnet. Jede Bewegung — Ausgabe an einen Goldschmied, Rückgabe, Guss, Schrott, Verlust — ist ein Beleg zwischen Lagerorten. Bearbeitungsverluste werden ausdrücklich erfasst, damit sich eine Inventur mit dem Buchbestand abstimmen lässt.

**Stack:** Odoo 17 Community, Python 3, PostgreSQL 17, OWL, QWeb-Berichte, Docker Compose, optional Anthropic API, Telegram Bot API, TSPL.

**Starten:** `docker compose up -d --build`, dann http://localhost:8069 öffnen, eine Datenbank anlegen und die Module installieren.

**Tests:** `./scripts/run_tests.sh` legt eine Wegwerf-Datenbank an, installiert alle Module von Grund auf und führt rund 200 Tests aus.

**Spezifikationen:** Neue Funktionen entstehen nach dem OpenSpec-Ansatz — Proposal, Delta-Spezifikation mit GIVEN/WHEN/THEN-Szenarien und Aufgabenliste je Änderung in `openspec/changes/`, der aktuelle Stand in `openspec/specs/`. Die Spezifikationen sind auf Russisch, der Arbeitssprache des Projekts.

**Lizenz:** [LGPL-3.0](LICENSE).
