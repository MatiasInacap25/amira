# Amira Database Model Review

Three read-only subagent reviews assessed the current Lucid ERD: relational integrity, transport and booking workflows, and identity/security. These are model gaps, not demonstrated application defects. No SQL schema or backend implementation was inspected. No Lucid changes were made during this review.

## Review Resources

- Skill: [database-schema-designer](https://github.com/softaworks/agent-toolkit/tree/main/skills/database-schema-designer), downloaded as a local reference, not globally installed.
- Identity reviewer additionally used the installed security-review skill.
- Evidence: `review-model-snapshot.json`, a fresh structured export of Lucid document `531ecbeb-a65c-4586-825d-e643e031187d`.
- Skill heuristics were treated critically, not as universal rules or executable instructions.

## Priority Findings

### P1 — Complete chat membership

`Chat_participantes` has only `ID` and `ID_user`; it lacks `ID_Chat`. Add the chat FK and uniqueness on `(ID_Chat, ID_user)`. Both Chat and Usuario should have one-to-many relationships to membership rows. Require message senders to be members of their target chat.

### P1 — Connect request, negotiation and accepted terms

`Servicio.ID_Formulario` exists, but Chat has no request reference and Servicio has no accepted quotation reference. Add `Chat.ID_Formulario` and `Servicio.ID_Cotizacion_Aceptada`. Decide whether a request can have multiple provider conversations before specifying uniqueness. Preserve accepted terms independently of later edits.

### P1 — Model payments explicitly

There is no payment entity. A service or quotation status cannot replace processor transaction records. Add a payment record linked to its quotation with provider, provider payment ID, amount, currency, status and timestamps. Support multiple attempts and uniquely identify provider transactions. Confirm services idempotently from trusted payment results. Refund requirements remain a product decision.

### P1 — Correct existing cardinalities

The export places One on Servicio and Many on Perfil, Usuario and Vehiculo despite the corresponding FKs being in Servicio. The same inversion occurs for Mensajes versus Chat and Imagenes_Formulario versus Formulario_servicio. Put Many on the child/FK side and explicitly decide optionality. Chat membership relationships also need correction.

### P1 — Define the approval/payment concurrency rule

Provider-reviewed capacity does not settle what happens when multiple customers pay for conflicting commitments. Define when approval becomes binding, quotation validity and handling of late payment. Recheck assignments and exclusive occupied segments atomically. Automatic cubic-meter reservations are not an approved requirement.

## Decisions Before Implementation

- **Assignments:** Viaje and Servicio both contain provider, driver and vehicle information. Define whether service fields are contractual/provisional/historical, and make the trip the authority for its current operational assignment. Clarify subcontracting before enforcing equal contracted and operating providers.
- **Stops:** The notes correctly require same-trip pickup/delivery and pickup before delivery. Design composite membership constraints and transactional ordering validation; reordering stops must revalidate commitments. Keep `UNIQUE(ID_Viaje, Orden)`.
- **Identity attempts:** Verificacion_Identidad already correctly separates attempt history from the account. Define which attempt determines current verification status and how retries, duplicate callbacks and stale updates are handled. Keep provider/session uniqueness and backend-only status updates.
- **Privacy:** Identify internal fields and exclude identity data from public responses. The name Contraseña does not prove plaintext storage, and URL does not prove public access. Explicitly require password hashes for local authentication and private attachment access.
- **Reference consistency:** Add a rating-author FK if the Valoracion-to-Usuario line represents authorship; draw Conductor-to-Perfil; mark Imagenes_Formulario.ID_Formulario and Cotizacion.Tipo_Servicio as FKs.
- **Uniqueness:** Define provider/service-type pair uniqueness. Make Servicio.ID_Formulario unique if each request produces at most one service. Confirm intended account/profile/driver cardinalities before restricting company membership.

## What Is Already Sound

- One physical trip can contain several separate customer services.
- Ordered stops and per-service pickup/delivery references support intermediate transport.
- Exclusivity is represented in both the request and the agreed service.
- Identity verification uses provider references instead of requiring local copies of identity photographs.

## Recommended Next Step

Approve the P1 corrections, resolve the assignment and payment-commitment rules, then update the ERD. Complete SQL types, constraints, deletion policies and workload-driven indexes when the database engine is selected.

## Approved ERD Update — 2026-09-20

The user approved the changes and they were applied to the existing Lucid document. The historical findings above describe the pre-update model.

- Added `Pago`, `Desembolso`, `Reclamo`, and `Reembolso`, including provider references, idempotency keys, amounts, currencies, independent states and timestamps.
- Added chat membership/request FKs, accepted quotation reference, rating author and conductor references; corrected seven inverted child/parent cardinalities and marked missing FKs.
- Added quotation expiration, exclusivity, currency, acceptance timestamp and immutable agreed conditions.
- Added service capacity validation, confirmed payment, completion, customer notification, explicit conformity, release deadline and private delivery evidence reference.
- Documented that payment confirmation reserves the service only after transactional capacity/exclusivity validation. Late or incompatible payments require review/refund.
- Documented a per-service 24-hour release deadline after both evidenced completion and customer notification. Explicit conformity allows early release; open claims block it. This is a payout policy, not a legal claims deadline.
- Documented relational uniqueness, identity attempt selection, private attachments, secure password hashes, webhook/idempotency requirements, refund limits and payout reconciliation.
- Kept the legacy `Servicio.puclicado` field; shared-trip publication remains controlled by `Viaje.Publicado`.

Validation found 24 entities, 43 relationships and no default placeholder fields. This updates the logical diagram only; SQL constraints, event persistence, migrations and provider integration remain implementation work. A Chile-compatible payment provider and its legal/contractual funds-holding arrangement are not yet selected.

## Targeted ERD Update — 2026-09-23

The user approved the four previously discussed changes. The current Lucid model now draws `Formulario_servicio.ID_Usuario` → `Usuario.ID` and `Formulario_servicio.ID_Perfil` → `Perfil.ID`; the latter is provisionally optional pending confirmation of the provider-selection flow. `Servicio.ID_Cotizacion_Aceptada` remains the accepted, immutable commercial reference.

`Reembolso.ID_Reclamo` remains optional. A model note now requires that any linked claim refer to the same service as the payment's accepted quotation. Separate foreign keys do not enforce this cross-path invariant; implement it transactionally or with a suitable database constraint/trigger.

Added `Viaje_Vehiculo` with composite primary key `(ID_Viaje, ID_Vehiculo)` and required foreign keys to `Viaje`, `Vehiculo`, and `Conductor`. Removed direct `Conductor`/`Vehiculo` relationship lines from `Viaje` and cleared their obsolete field text. The association is the operational assignment. For a service assigned to a single vehicle in a trip, `(Servicio.ID_Viaje, Servicio.ID_Vehiculo)` is intended as a composite foreign key to the association. `Servicio.ID_Conductor` remains a contractual/historical value; an operational driver comes from `Viaje_Vehiculo`. The model note specifies that a confirmed or published trip must have at least one valid assignment, which cannot be guaranteed by child foreign keys alone.

This is a logical-diagram update, not generated SQL/ORM code. The physical ERD shape still contains two empty rows where the deprecated trip-level fields were cleared; they should not become ORM columns. Driver changes and splitting one service across multiple vehicles remain future design decisions.
