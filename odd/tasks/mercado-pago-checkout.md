# Mercado Pago test checkout
Objective: charge customer quotations through Checkout Pro in Chile's test environment. Planned branch: feat/mercado-pago-checkout.
Delivery: feature-branch-chain; estimated 600–900 authored lines. Runners: pytest and Playwright.

## Specs
- S1: “en la parte de pagos quiero que en vez de simularlos hacerlos con mercado pago y poder hacerlo con los datos d eprueba que dan”. Customer quotation checkout only; refunds and payouts remain simulated.
- S2: Confirm payment from provider evidence, never from the browser return. Preserve approved late payments without creating a service when the quotation expired or was replaced; display “Pago en revisión”.

## Tasks
- T1 (S1–S2) Backend checkout, verified confirmations, reconciliation and regression tests — implemented, delegated (independent backend and frontend surfaces).
- T2 (S1–S2) Customer result display, sandbox test guide and browser tests — implemented, delegated (independent backend and frontend surfaces).
- T3 (S1–S2) Independent verification and integration checks — verified with limitations, delegated (credentials, public confirmation contract and concurrency).

## Log
- L1: en la parte de pagos quiero que en vez de simularlos hacerlos con mercado pago y poder hacerlo con los datos d eprueba que dan
- L2: User confirmed “si” to customer checkout only and “si” to retaining late approvals for review.
- L3: Existing confirmation marks late approvals rejected. Current branch contains unrelated company driver work. No remote operations authorized.
- L4: “me parece bien esa estrategia”. Separate backend and frontend slices on local integration branch; no push or deployment.
- L5: Backend focused 96 passed, one PostgreSQL skip; browser 47 passed before corrections, clean typecheck passed. Independent recheck cleared rejection persistence, review copy and RLS coverage. Actual sandbox purchase, PostgreSQL migration and concurrency not verified; unrelated baseline date-sensitive test fails.
