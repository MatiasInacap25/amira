# Viajes compartidos

Objective: implement items 8 and 10 of the Notion page "Cambios Amira": the customer's sharing choice in the quote request, and shared trips as an option of contracted services instead of a service type.
Branch: feat/viajes-compartidos (from main 15a1610). Delivery strategy: ask-on-risk, chain strategy stacked to main through develop. Test runners: `uv run pytest` (backend), `node --test tests/unit/*.mjs` and Playwright (frontend).

## Specs

- S1 (item 8): "Agregar a la cotización inicial del cliente si el servicio se puede compartir con un campo de select que venga por defecto marcado como que el usuario no acepta". User clarification: "en la cotizacion el select de si eel cliente quiere permitir compartir el viaje con otro cliente por defecto el valor base sea que no, esto en caso de que el cliente se le olvide o lo pase por alto". The choice is stored on the request (`es_exclusivo` = not accepted), carried to the quotation and the service, and shown to the provider. Existing rows stay as they are.
- S2 (item 10): "Cambiar que “Rutas compartidas” no es un tipo de servicio, es una opcion de los servicios que si alguien contrata un servicio (ejemplo: de santiago a valparaiso) el usuario puede acceder/aceptar a compartir el vehiculo con otro usuario y el proveedor si considera tambien que puede compartirse el espacio del vehiculo, esta puede publicar el traslado (santiago a valparaiso) y la fecha y que otro usaurio se sume al viaje y asi le saldria mas barato al segundo usuario y se aprovecharia un viaje para hacer 2 servicios". Approved rules:
  - The shared trip comes only from a contracted (paid) service whose customer accepted sharing; the provider publishes it, copying origin, destination and date.
  - A second customer joins from the `/rutas-compartidas` list with a request tied to that trip; the provider accepts or rejects and quotes as usual, with its own chat and payment.
  - The second customer may pick up and deliver at stops along the route; the provider decides whether it fits.
  - Capacity is not calculated: the provider decides per request and can close the trip to new requests.
  - Price is a free quotation by the provider; the first customer's payment does not change and there are no automatic refunds.
  - If the first customer cancels, the trip and the other services continue; each service is independent.
- S3 (item 10): the "Carga compartida" service type is hidden from the catalog, filters and provider profile; existing rows that reference it stay valid.
- Assumption, not confirmed by the user: chats stay separate per customer, and customers do not see each other's data, as `PROJECT_OVERVIEW.md` states.
- Known gap accepted by the user's choice in S1: services created before S1 read as shareable although no customer chose it, so they could be published.

## Tasks

- [x] T1, S1, delegated (herdr worker-5): sharing select in the quote modal, payload field, request, quotation and service carry the choice, provider label. Backend RED observed (5 failures); frontend RED not observed. Backend 773 passed, Playwright 44 of 44 on marketplace and request detail, unit 158, lint clean.
- [ ] T2, S3, delegated (after T1, herdr worker): hide the "Carga compartida" type.
- [ ] T3, S2 backend, delegated (after T1, herdr worker): publish a shared trip from a paid shareable service, close it, list it, join request tied to the trip with stops, link the paid service to the trip. High risk: permissions and persisted data.
- [ ] T4, S2 frontend, delegated (after T3, herdr worker): provider publish and close actions, "Sumarme" on `/rutas-compartidas`, trip shown in request and service details.
- [ ] T5, delegated (herdr reviewer): independent verification and Codex gpt-6.1-sol native gentle-ai review.

Route evidence: sequential herdr workers per the project orchestrator rule. T1, T2 and T3 all edit `public_routes.py`, so they are not disjoint and run one after another; T4 depends on T3's contract. The parent owns git.

## Log

- L1 (2026-11-07), user's request: "no las borres, vamos con los items 8 y 10". Answers: trip origin "De un servicio contratado"; joining "Solicitud desde la lista"; route "Paradas dentro de la ruta"; capacity "Lo decide el proveedor"; price "Cotización libre"; cancellation "El viaje sigue"; old type "Ocultarlo (Recomendado)"; old rows: "dejalas como esta, con eso de que por defecto vengan si marcar me refiero a que en la cotizacion el select de si eel cliente quiere permitir compartir el viaje con otro cliente por defecto el valor base sea que no, esto en caso de que el cliente se le olvide o lo pase por alto".
- L2: map from a read-only explorer. `es_exclusivo` exists on request, quotation and service but is hardcoded to false at `public_routes.py:264` and `quotation_routes.py:74` (parent spot check confirmed). Trip tables `Viaje`, `Viaje_Vehiculo`, `Parada_Viaje` exist, with no endpoint creating them; capacity locking is documented, not implemented.
