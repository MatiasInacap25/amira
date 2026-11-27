# IVA Breakdown and Simulated Tax Documents

Objective: show the IVA breakdown of every quoted/paid amount to customers and providers, and issue simulated tax documents (customer boleta in the carrier's name, Amira's commission invoice to the carrier) for the final demo. Sandbox only: documents are simulated, never sent to the SII.
Branch: `feat/tax-documents`, based on `chore/next-16.4.6` (PR #71). Shared tree, parent owns git: workers do NOT commit, push, switch branches, run repo-wide formatters or installs. Runners: backend `uv run pytest` (from `backend/`); frontend `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npx playwright test` (from `frontend/`).
Requirements source: `docs/requisitos/modelo-b-lo-que-falta.md` rows 25, 28, 53, 64c (adapted to the mandate model).

## Specs

### S0. Business rules (fixed, do not change)
- Mandate model: the carrier sells the freight; Amira collects by mandate and earns a commission it invoices to the carrier.
- Every quoted amount **includes IVA 19 %**. IVA is extracted, never added: `net = round_half_up(total / 1.19)` to whole CLP, `iva = total - net`. Example: 80.000 → net 67.227, IVA 12.773.
- Commission: the existing `commission_for(gross, payout_commission_percent)` (10 %, whole CLP, half up). Its IVA is extracted the same way. Example: 80.000 → commission 8.000 = net 6.723 + IVA 1.277; carrier receives 72.000.
- Amounts are CLP whole pesos in every new API field (ints), even though the DB columns are `Numeric(18,4)`.

### S1. Breakdown functions (backend, pure)
- New module `backend/src/amira_api/tax.py`: `IVA_RATE_PERCENT = 19`; `split_iva(total: int) -> tuple[int, int]` returning `(net, iva)` per S0; `amount_breakdown(total: int, commission_percent: int) -> AmountBreakdown` (dataclass) with `total, net, iva, commission, commission_net, commission_iva, carrier_amount`. Reuse `commission_for` from `payout_service.py` (do not reimplement the rounding).
- Unit tests with the S0 examples, 0, 1, 119, 10001 and a value where half-up matters.

### S2. API fields (backend)
- `Quotation` response (`quotation_schemas.py`, built in `quotation_service.quotation_view`): add `net_amount: int` and `iva_amount: int`. It is embedded in the chat timeline, so both roles get it.
- `ServiceDetail` (`provider_service_schemas.py`, built in `service_views.py`): add `amount_breakdown: AmountBreakdownView | None` (None when the service has no amount). Fields: `total, net, iva` always; `commission, commission_net, commission_iva, carrier_amount` only when `viewer_role` is the provider side (null for the customer). Use the configured `payout_commission_percent`.
- Nothing is stored for the breakdown; it is computed.
- Update the backend tests that compare whole response dicts (`test_provider_service_routes.py:180-192` if the list item changes — it should NOT change; `ServiceDetail` tests; `test_quotation_routes.py`).

### S3. Simulated tax documents (backend)
- New model `TaxDocument`, table `"Documento_Tributario"`: `ID` (UUID PK, `gen_random_uuid()`), `ID_Servicio` (FK Servicio, not null, indexed), `ID_Pago` (FK Pago, nullable), `ID_Desembolso` (FK Desembolso, nullable), `Tipo` (String(40): `boleta` | `factura_comision`, CHECK), `Folio` (Integer, not null), `Emisor_Nombre`, `Emisor_Rut`, `Receptor_Nombre`, `Receptor_Rut` (String, receptor RUT nullable), `Neto`, `IVA`, `Total` (Numeric(18,4), non-negative CHECKs), `Moneda` (String(3) CHECK 'CLP'), `Emitido_En` (timestamptz), `Simulado` (Boolean, not null, default true). Unique (`ID_Servicio`, `Tipo`) — one document of each type per service. Unique (`Tipo`, `Folio`).
- Additive Alembic migration after `20261123_0001` (RLS enabled, privileges revoked from PUBLIC/anon/authenticated, like the previous migrations; add the table to `test_public_db.py` expectations).
- Folio: next integer per `Tipo` (max + 1) computed inside the same transaction; the unique (`Tipo`, `Folio`) constraint is the guard.
- **Boleta** (customer document, issued in the carrier's name by mandate): created in `payment_service.confirm_payment` in the same transaction that creates the `Servicio` when the payment is approved (covers Mercado Pago webhook, reconciliation and the simulated path through `_apply_confirmation`). Emisor = carrier: `Perfil.name` and `Perfil.company_tax_id`, or for an independent driver the owner `Usuario` full name and `national_id`. Receptor = customer `Usuario` full name and `national_id`. Amounts = `split_iva(payment amount)`. Idempotent: a replayed confirmation must not create a second boleta (unique constraint + insert ON CONFLICT DO NOTHING, like `Aceptacion_Terminos`).
- Assumption (logged): there is no customer company/tax data yet, so every customer gets a `boleta`; `factura` for company customers is out of scope.
- **Factura de comisión** (Amira → carrier): created in `payout_service._release_one` in the same transaction as the `Desembolso`. Emisor = Amira from new settings `amira_legal_name` (default `"[DEMO] Amira SpA"`) and `amira_tax_id` (default `"76.000.000-0"`) in `settings.py` + `.env.example`. Receptor = the carrier (same rule as the boleta emisor). Amounts = the commission split (`commission_net`, `commission_iva`, `commission`). Idempotent the same way.
- Endpoints (reuse the existing authorization of the service detail routes; same 404 rules):
  - `GET /api/customer/services/{serviceId}/documents` → the service's `boleta` only.
  - `GET /api/provider/services/{serviceId}/documents` → the `boleta` and the `factura_comision`; only the provider profile owner (employed drivers get 403/404 like other money data — follow the existing rule for amounts).
  - Response item: `id, type, folio, issued_at, issuer_name, issuer_tax_id, recipient_name, recipient_tax_id, net, iva, total, currency, simulated, service_id`.
- Tests: boleta created once on approval (also on replay), amounts for 80.000, emisor for company vs independent driver; factura created on payout release with 8.000/6.723/1.277; customer cannot see the factura; unrelated user gets 404; folios increase.

### S4. Frontend
- Shared helper `frontend/src/lib/tax.ts` mirroring S1 (`splitIva`) for the quotation dialog preview, with node unit tests using the S0 examples. Use the existing `formatClp` (`lib/chat-quotations.ts`) for money.
- Quotation dialog (`components/marketplace/quotation-dialog.tsx`): label "Monto total (IVA incluido)" and a live hint under the input: "Neto $67.227 · IVA $12.773" (computed with `splitIva`).
- Chat quote card (`components/marketplace/chat-quotation-card.tsx`): keep the total, add the caption "IVA incluido" and a line "Neto $X · IVA $Y" from the API fields.
- Service detail (`components/marketplace/service-detail.tsx`): replace the single "Monto" fact with "Total (IVA incluido)", "Neto", "IVA". For the provider also "Comisión Amira (IVA incluido)" and "Recibirás" (`carrier_amount`).
- Service detail gets a "Documentos" section listing the documents from S3 (type label "Boleta" / "Factura de comisión", folio, total, issued date) with a "Ver" button that opens an accessible modal (reuse the dialog pattern of `components/legal/terms-dialog.tsx`) rendering the document as a printable receipt: header with type and "Folio N°", a visible banner "DOCUMENTO SIMULADO · SIN VALIDEZ TRIBUTARIA", emisor and receptor (name + RUT), date, a line "Servicio de transporte" (boleta) or "Comisión por intermediación" (factura) and Neto / IVA 19 % / Total; a "Imprimir" button (`window.print()`, print CSS hides the rest of the page). Empty state: "Aún no hay documentos para este servicio."
- Update `lib/marketplace-api.ts` / `lib/chats.ts` types and the Playwright fixtures/expectations (`page-chat.spec.ts`, `page-cuenta-servicio-detalle.spec.ts`), and add Playwright tests: quote card shows the breakdown; customer detail shows total/neto/IVA and no commission; provider detail shows commission and "Recibirás"; documents modal opens with the simulated banner and closes with Escape.

## Tasks

| ID | Specs | Route | Status | Commit |
|---|---|---|---|---|
| T1 | S0, S1, S2, S3 | delegated (backend worker, herdr) | pending | |
| T2 | S0, S4 (contract from S2/S3) | delegated (frontend worker, herdr) | pending | |

Route reason: project CLAUDE.md orchestrator role under `HERDR_ENV=1`; two units with disjoint edit surfaces launched together. Risk: high (money path in `confirm_payment` and `_release_one`, new migration) → independent review after checks.

## Log

- L1 (2026-11-24, user): "cuando termine y pase todo los test sigue con el siguiente punto sin preguntarme" — next point of the demo list: "Desglose con IVA y documento al cliente (25, 28, 17)", adapted by the earlier user decisions "con iva incluido, y como estaba en el archivo vamos a usar el modelo de mandato".
- L2: Coordination: `feat/admin-panel` (Codex) also adds a migration after `20261123_0001`; whichever branch merges second must rebase its `down_revision` to keep a single Alembic head.
