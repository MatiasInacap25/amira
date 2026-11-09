# Informe de pruebas de caja negra de Amira

Fecha de ejecución: 9 de noviembre de 2026. Rama: `test/caja-negra`.
Especificación de campaña: [caja-negra.md](../../odd/tasks/caja-negra.md), S1–S7.

## Resumen ejecutivo

La campaña final de backend obtuvo **195 pruebas aprobadas, 0 fallidas, 1 fallo esperado estricto y 0 omitidas**. El fallo esperado corresponde a la reutilización de un enlace de pago documentado como de un solo uso. La repetición devolvió aprobación, pero no creó un segundo servicio.

La suite existente ejecutada con Playwright obtuvo **427 aprobadas, 0 fallidas, 0 inestables y 0 omitidas**, distribuidas en **31 archivos**. Este resultado incluye pruebas de funciones ejecutadas por Playwright: no equivale a 427 recorridos completos contra el backend real.

La suite predeterminada de backend **no está completamente verde**: registró **856 aprobadas, 1 fallida y 199 omitidas**. El mismo fallo se reprodujo excluyendo el directorio nuevo, con **856 aprobadas, 1 fallida y 3 omitidas**. Por tanto, la campaña no introdujo ese fallo, pero tampoco lo corrigió: la restricción de superficies no autoriza modificar la prueba existente. No se presenta este resultado como una validación global satisfactoria.

## 1. Objetivo y alcance

Verificar el comportamiento observable frente a las especificaciones mediante HTTP real, con PostgreSQL desechable, autenticación firmada localmente y separación entre actores. Se evaluaron catálogo público, cuentas, solicitudes, cotizaciones, pagos simulados, servicios, ubicación, evidencia de entrega, reclamos, conformidad, elegibilidad de desembolsos, chat, imágenes, publicación del perfil, vehículos, invitaciones y viajes compartidos.

Se agregaron los nueve módulos de áreas exigidos por S4 y un módulo de comprobación del arnés. Se mantuvieron intactos `backend/src/**`, `frontend/src/**`, las migraciones, las dependencias y los archivos de pruebas de Playwright. No se cambió de rama ni se publicó contenido remoto.

El esquema servido contenía **58 rutas y 64 operaciones**. Estos números describen el contrato expuesto; **no se afirma cobertura exhaustiva de esas operaciones ni cobertura de líneas de código**. Las variantes efectivamente ejecutadas se identifican en la matriz de trazabilidad.

## 2. Por qué son pruebas de caja negra

El oráculo se limitó a `PROJECT_OVERVIEW.md`, las secciones funcionales de `backend/README.md`, las secciones `## Specs` de los documentos de tareas y `/openapi.json` obtenido del proceso real. Cada función de prueba cita su fuente en la documentación interna.

No se importaron módulos de aplicación para formular aserciones, sustituir dependencias ni instanciar un cliente ASGI. Las solicitudes atravesaron el socket HTTP del servidor Uvicorn. La lectura de migraciones y el SQL se utilizaron para preparar datos con los nombres físicos documentados y comprobar efectos persistidos, no para inferir respuestas esperadas desde la implementación.

Cuando el contrato no fija un código concreto para un rechazo, la comprobación puede aceptar la clase de rechazo documentada. Para D1 se exige una respuesta de rechazo de cliente, sin inventar un código exacto. Durante la revisión final se retiraron expectativas específicas sobre repetición de decisiones de solicitudes, cuyo comportamiento no está definido en las fuentes autorizadas. Esa falta de definición se conserva como ambigüedad.

## 3. Entorno y arnés

| Elemento | Configuración observada |
|---|---|
| Python | 3.12.15 |
| pytest | 8.4.2 |
| Uvicorn | 0.54.0 |
| HTTPX | 0.28.1 |
| Psycopg | 3.3.6 |
| PyJWT / cryptography | 2.15.0 / 50.0.1 |
| PostgreSQL | 17.11; revisión Alembic `20261108_0001` |
| Base autorizada | `postgresql://postgres:postgres@127.0.0.1:55432/postgres`, contenedor desechable `amira_blackbox_db`, TLS requerido |
| API | Subproceso `python -m uvicorn amira_api.main:app`, host `127.0.0.1`, puerto libre, `APP_ENV=test` |
| Autenticación | Servidor HTTP JWKS local, clave RSA generada por sesión, RS256; sujetos de cliente, otro cliente, dueño, otro dueño y conductor |
| JWT | `iss`, `aud`, `exp`, `iat`, `sub`, `aal`, `amr`, `session_id`, `email`, `role`, `is_anonymous` |
| Storage | Doble HTTP local en memoria: registra cargas, responde solicitudes de firma y reconoce eliminación; no es Supabase real |
| Desembolsos | Subproceso real `python -m amira_api.release_payouts`, adaptador simulado y la misma base desechable |
| Frontend | Node v26.12.0; Playwright 1.63.0, Chromium instalado; aplicación aislada en `127.0.0.1:3179`, autenticación falsa en `127.0.0.1:54329` |

### Aislamiento y seguridad de ejecución

- La selección depende exclusivamente de `AMIRA_BLACKBOX_DATABASE_URL`; no se reutiliza `DATABASE_URL` del entorno del ejecutor.
- Se aplica `destructive_test_skip_reason` de `tests/postgres_support.py` y una restricción adicional: host literal `127.0.0.1`, puerto `55432`, base `postgres` y ninguna opción de consulta. Se rechazan redirecciones libpq conocidas.
- La ausencia de la variable omite el directorio antes de abrir conexiones. Una comprobación específica con la URL del puerto prohibido `54322` produjo **196 omitidas en 0,06 s**, mediante la guarda, sin solicitar conexión a ese puerto.
- El arnés trunca `Usuario CASCADE` entre escenarios autenticados y vuelve a crear actores, perfiles y vehículos de prueba. **Destruye datos de esa base desechable**; no debe utilizarse como una suite no destructiva.
- El proceso de aplicación recibe un entorno construido expresamente, sin credenciales remotas, y se inicia desde un directorio temporal vacío para evitar cargar `.env` del repositorio.
- Las fechas funcionales se calculan respecto de la ejecución; no se espera el transcurso real de ventanas comerciales. La única pausa explícita en las pruebas es el sondeo acotado de disponibilidad de Uvicorn.
- Playwright utilizó un preloader Node que restringe sockets/DNS y propaga la restricción a procesos hijos, y un lanzador Chromium con proxy de rechazo local para destinos no locales. Se deshabilitó la descarga automática de paquetes. No se instalaron dependencias ni navegadores.
- La comprobación suplementaria del lanzador versionado y su guarda reforzada pasó un escenario existente de viajes compartidos. La medición completa de 427 corresponde a la primera ejecución con los equivalentes temporales; no se mezcla ese escenario adicional con el total de la campaña completa.

### Comandos ejecutados

Backend completo con evidencia XML:

```bash
cd backend
AMIRA_BLACKBOX_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres uv run pytest tests/blackbox -v --junitxml=/tmp/amira-bb-final.xml
```

Comprobación predeterminada, sin activar caja negra, y referencia sin el directorio nuevo:

```bash
cd backend
uv run pytest -q --junitxml=/tmp/amira-bb-default-final.xml
uv run pytest --ignore=tests/blackbox -q
```

Comprobación de rechazo de la configuración prohibida; el comando solo ejercita la guarda:

```bash
cd backend
AMIRA_BLACKBOX_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run pytest tests/blackbox -q
```

Playwright completo, con los lanzadores temporales usados en la medición:

```bash
cd frontend
NODE_OPTIONS=--require=/tmp/amira-bb-local-only.cjs \
NEXT_TELEMETRY_DISABLED=1 npm_config_offline=true npm_config_update_notifier=false \
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/tmp/amira-bb-chromium \
PLAYWRIGHT_JSON_OUTPUT_NAME=/tmp/amira-bb-playwright.json \
npx playwright test --reporter=line,json --output=/tmp/amira-bb-playwright-artifacts
```

Forma reutilizable con los lanzadores conservados en el repositorio; requiere un Chromium ya instalado, sin descargarlo:

```bash
cd frontend
AMIRA_BLACKBOX_CHROMIUM_EXECUTABLE="$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome" \
NODE_OPTIONS="--require=$PWD/../backend/tests/blackbox/local_only_node.cjs" \
NEXT_TELEMETRY_DISABLED=1 npm_config_offline=true npm_config_update_notifier=false \
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="$PWD/../backend/tests/blackbox/local_chromium.sh" \
PLAYWRIGHT_JSON_OUTPUT_NAME=/tmp/amira-bb-playwright.json \
npx playwright test --reporter=line,json --output=/tmp/amira-bb-playwright-artifacts
```

La comprobación suplementaria ejecutó esta última forma agregando `tests/page-cuenta-viajes-compartidos.spec.ts`, con salida JSON separada `/tmp/amira-bb-playwright-guard-smoke.json`: **1 aprobada**, informada por consola en **8,1 s**. Además se comprobaron directamente dos formas de conexión no local en Node, rechazadas antes de conectar.

Los XML, JSON, registros y artefactos bajo `/tmp` son evidencias temporales de esta ejecución, no archivos versionados ni un requisito para recolectar las pruebas. Las tablas de este informe preservan sus resultados; repetir los comandos genera nuevas mediciones.

## 4. Técnicas aplicadas por área

| Área / módulo | Particiones y límites | Tabla de decisión / errores | Transiciones observadas |
|---|---|---|---|
| Catálogo público | `limit` 0/1/50/51; `offset` 0/5000/5001; `q` 120/121; CUT de región 1/2/3 dígitos y letras, comuna 4/5/6 y letras; UUID malformado/desconocido; fecha con/sin zona | Respuesta pública sin correo, RUT ni claves privadas; tipo oculto excluido | Navegación y filtros; no hay escritura |
| Cuenta / autenticación | JWT ausente, malformado, vencido; emisor/audiencia incorrectos; código de respaldo con longitud/formato incorrectos | AAL1/AAL2, anónimo, rol y correo; identidades de cliente/dueño/conductor; campos extra | Rechazo sin crear desafíos de respaldo |
| Solicitudes / cotizaciones | Direcciones vacías/excesivas, comuna/UUID inválidos, carga negativa, campos extra; CLP entero positivo; vigencia 0/1/168/169; descripción 0/1000/1001 | Actor de servidor, proveedor participante frente a otros actores, acceso cruzado | Solicitud → aceptación y chat → cotización; rechazo de solicitud y cotización; pago de cotización rechazada sin reserva |
| Pagos | Token manipulado, propietario/no propietario; secreto webhook ausente/incorrecto/correcto | Webhook no autoriza adaptador simulado; cliente de otra operación no consume el enlace | Aprobación → un servicio confirmado; rechazo → sin servicio; repetición de pago y de enlace consumido (D1) |
| Servicios / ubicación | Asignación vacía/UUID inválidos/campos extra; GPS fuera de límites y extremos inclusivos; foto vacía/no imagen/8 MiB/8 MiB+1 | Dueño, conductor asignado, cliente y terceros; dueño no asignado no actualiza GPS | Confirmado → en curso con primera posición → completado con foto; inicio inválido sin escritura; completar antes de iniciar; segundo inicio; posición eliminada y lectura 404 al completar |
| Reclamos / desembolsos | Motivo vacío/blancos/1/1000/1001; ventana cerrada preparada con SQL | Cliente ajeno; consentimiento frente a reclamo; cuenta habilitada/ausente y pago aprobado/ausente | Completado → conformidad o disputa; reclamo bloquea conformidad; elegibilidad por conformidad o vencimiento, idempotencia del desembolso, comisión neta |
| Chat | Mensaje 0/1/2000/2001; adjunto no imagen/5 MiB/5 MiB+1 | Participante/no participante; token SSE en URL rechazado; stream autenticado | Mensaje/cotización en línea temporal plana; conteo no leído por contraparte; marcar leído 204 y repetición sin incrementar |
| Perfil / vehículos / imágenes | Guardado incompleto/extra/desconocido; año 1885/1886/2200/2201, peso 0/1; JPEG/PNG/WebP por bytes; 5 MiB/5 MiB+1; cinco/seis imágenes | Dueño frente a cliente/conductor; matrícula normalizada duplicada; vehículo ajeno mismo 404 que inexistente | Borrador → publicación → aparición pública → despublicación; guardado incompleto despublica; vehículo asignado no se elimina |
| Invitaciones / viajes compartidos | Correo y token inválidos, campos extra; compartir explícito frente a falso/omitido | Dueño de empresa/no dueño; invitación ajena; viaje de otro perfil y cerrado | Publicación de servicio pagado compartible; cierre preserva vínculos; exclusividad impide publicar; segundo cliente aceptado y pagado se enlaza incluso tras cierre, con chat/servicio separados y cuatro paradas ordenadas |

## 5. Resultados de backend por módulo

El XML de pytest agrupa `xfail` dentro de omisiones. Aquí se separa expresamente para no confundir un defecto conocido con una prueba no ejecutada.

| Módulo | Aprobadas | Fallidas | xfail estricto | Omitidas |
|---|---:|---:|---:|---:|
| `test_bb_auth_account.py` | 18 | 0 | 0 | 0 |
| `test_bb_chat.py` | 13 | 0 | 0 | 0 |
| `test_bb_claims_payouts.py` | 16 | 0 | 0 | 0 |
| `test_bb_harness.py` | 2 | 0 | 0 | 0 |
| `test_bb_invitations_shared_trips.py` | 19 | 0 | 0 | 0 |
| `test_bb_payments.py` | 7 | 0 | 1 | 0 |
| `test_bb_provider_profile_vehicles.py` | 25 | 0 | 0 | 0 |
| `test_bb_public_browse.py` | 41 | 0 | 0 | 0 |
| `test_bb_requests_quotations.py` | 29 | 0 | 0 | 0 |
| `test_bb_services_lifecycle.py` | 25 | 0 | 0 | 0 |
| **Total** | **195** | **0** | **1** | **0** |

Duración final de pytest: **16,66 s** (XML: 16,664 s). El resultado estricto esperado es D1; no se ocultaron otros fallos mediante `xfail`.

## 6. Resultados de Playwright por archivo

Fuente: reporte JSON de la campaña completa. Todos los resultados individuales tuvieron estado `passed`. No hubo reintentos que permitieran demostrar estabilidad entre ejecuciones: **0 flaky observado no significa ausencia general de intermitencias**.

| Archivo existente | Aprobadas | Fallidas | Inestables | Omitidas |
|---|---:|---:|---:|---:|
| `account-query-cache.spec.ts` | 1 | 0 | 0 | 0 |
| `auth-config.spec.ts` | 2 | 0 | 0 | 0 |
| `auth.spec.ts` | 19 | 0 | 0 | 0 |
| `driver-invitation.spec.ts` | 6 | 0 | 0 | 0 |
| `header-profile-menu.spec.ts` | 6 | 0 | 0 | 0 |
| `header-roles.spec.ts` | 8 | 0 | 0 | 0 |
| `home.spec.ts` | 35 | 0 | 0 | 0 |
| `marketplace.spec.ts` | 29 | 0 | 0 | 0 |
| `page-chat.spec.ts` | 36 | 0 | 0 | 0 |
| `page-cuenta-invitaciones.spec.ts` | 20 | 0 | 0 | 0 |
| `page-cuenta-perfil-proveedor.spec.ts` | 22 | 0 | 0 | 0 |
| `page-cuenta-servicio-detalle.spec.ts` | 39 | 0 | 0 | 0 |
| `page-cuenta-servicios.spec.ts` | 16 | 0 | 0 | 0 |
| `page-cuenta-vehiculos.spec.ts` | 5 | 0 | 0 | 0 |
| `page-cuenta-viajes-compartidos.spec.ts` | 1 | 0 | 0 | 0 |
| `page-invitacion-aceptar.spec.ts` | 8 | 0 | 0 | 0 |
| `page-invitacion-conductor.spec.ts` | 6 | 0 | 0 | 0 |
| `page-login.spec.ts` | 9 | 0 | 0 | 0 |
| `page-mensajes.spec.ts` | 17 | 0 | 0 | 0 |
| `page-not-found.spec.ts` | 4 | 0 | 0 | 0 |
| `page-pago-resultado.spec.ts` | 8 | 0 | 0 | 0 |
| `page-pago-simulado.spec.ts` | 10 | 0 | 0 | 0 |
| `page-panel.spec.ts` | 7 | 0 | 0 | 0 |
| `page-prestador.spec.ts` | 14 | 0 | 0 | 0 |
| `page-registro.spec.ts` | 12 | 0 | 0 | 0 |
| `page-rutas-compartidas.spec.ts` | 15 | 0 | 0 | 0 |
| `page-servicios.spec.ts` | 12 | 0 | 0 | 0 |
| `page-solicitud-detalle.spec.ts` | 18 | 0 | 0 | 0 |
| `page-solicitudes.spec.ts` | 8 | 0 | 0 | 0 |
| `rut-caret.spec.ts` | 4 | 0 | 0 | 0 |
| `rut.spec.ts` | 30 | 0 | 0 | 0 |
| **Total** | **427** | **0** | **0** | **0** |

Duración JSON: **499969,815 ms**; consola: **8,3 minutos**. Inicio registrado: `2026-11-09T21:04:03.820Z`.

### Flujos sin cobertura E2E integral

La identificación se basó en los escenarios y títulos de las pruebas existentes, no en inspección de componentes:

1. **Solicitud → aceptación del proveedor → cotización → pago → asignación → ubicación → entrega → conformidad/reclamo → desembolso en un mismo recorrido con persistencia real.** Hay escenarios de interfaz separados con respuestas falsas y una campaña HTTP real, pero no una prueba que una navegador y base real durante toda la cadena (S3).
2. **Segundo cliente que se incorpora a un viaje, recibe cotización, paga y obtiene paradas persistidas con aislamiento respecto del primer cliente.** Los archivos de rutas compartidas, detalle de solicitud y viajes compartidos prueban partes de la interfaz; el recorrido persistente de dos clientes fue probado por HTTP, no íntegramente por navegador (`viajes-compartidos.md S2`).
3. **Entrega del correo de invitación y alta real del conductor mediante un proveedor externo, seguida de uso del servicio asignado.** Los escenarios actuales simulan autenticación y aceptación; no comprueban el envío externo ni una sesión Supabase real.
4. **Reproducción visual de archivos privados reales y vencimiento efectivo de sus URL firmadas.** Las imágenes y mapas usan respuestas controladas; no se validan políticas Storage ni expiración real (`chat-completion.md S3`, README de fotos e imágenes).
5. **Liberación de desembolso por vencimiento de la ventana sin conformidad, o bloqueo por reclamo, observada desde una sesión de usuario real.** El trabajo programable no tiene recorrido de navegador integral; se ejecutó su comando local simulado (README de reclamos y desembolsos).
6. **Expiración real del enlace de pago de quince minutos y límites de sesiones SSE con autenticación real.** La cobertura de interfaz sobre estados de cotización vencida o reconexión no demuestra estas reglas del servidor (README de pagos y eventos).

## 7. Matriz de trazabilidad

Cada fila identifica una función ejecutada mediante su **ID de pytest**. Cuando hay parámetros, el prefijo incluye todas sus variantes `[... ]`; el conteo indica cuántas variantes se midieron. Las rutas son relativas a `backend/tests/blackbox/`. La referencia de fuente se conserva de la documentación interna de cada prueba.

| Fuente / requisito comprobado | ID de prueba (prefijo) | Aprobadas | Fallidas | xfail | Omitidas |
|---|---|---:|---:|---:|---:|
| README.md#development-only-sms-mfa-bypass: signature/issuer/audience/expiry/role/email/anonymous checks. | `test_bb_auth_account.py::test_authentication_decision_table` | 9 | 0 | 0 | 0 |
| OpenAPI AccountResponse: account identity and role come from verified JWT, not caller JSON. | `test_bb_auth_account.py::test_verified_actor_identity` | 4 | 0 | 0 | 0 |
| OpenAPI EmailCodeRequest: six digits, additionalProperties=false; no malformed proof writes. | `test_bb_auth_account.py::test_email_fallback_validation` | 5 | 0 | 0 | 0 |
| OpenAPI ChatMessageCreate: content length 1..2000; odd/tasks/caja-negra.md S3 boundary partitioning. | `test_bb_chat.py::test_message_length_boundaries` | 4 | 0 | 0 | 0 |
| README.md#chat-attachments-private-supabase-storage-bucket; odd/tasks/caja-negra.md S3 participant IDOR. | `test_bb_chat.py::test_chat_participant_idor` | 3 | 0 | 0 | 0 |
| odd/tasks/chat-completion.md S1, S4: flat timeline, own messages/quotes excluded, mark read returns 204. | `test_bb_chat.py::test_timeline_and_unread_read_transition` | 1 | 0 | 0 | 0 |
| README.md#chat-attachments-private-supabase-storage-bucket: magic-byte MIME, 5 MiB limit. | `test_bb_chat.py::test_attachment_size_and_magic_type` | 3 | 0 | 0 | 0 |
| README.md#chat-real-time-events: Authorization required; JWT must not be accepted from URL. | `test_bb_chat.py::test_sse_token_is_never_read_from_url` | 1 | 0 | 0 | 0 |
| README.md#chat-real-time-events: authenticated per-user text/event-stream, ready/degraded state. | `test_bb_chat.py::test_sse_is_authenticated_event_stream` | 1 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: trimmed reason 1..1000, claim moves service to disputed. | `test_bb_claims_payouts.py::test_claim_boundaries` | 5 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: consent records satisfaction; no claim after consent. | `test_bb_claims_payouts.py::test_consent_and_claim_are_mutually_exclusive` | 1 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: one customer action, open claim blocks consent. | `test_bb_claims_payouts.py::test_open_claim_blocks_consent_and_duplicate_claim` | 1 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: only owning customer may act on a completed service. | `test_bb_claims_payouts.py::test_customer_actions_before_completion_and_idor` | 2 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: claim refused after configured 24-hour window. | `test_bb_claims_payouts.py::test_claim_window_closed` | 1 | 0 | 0 | 0 |
| README.md#claims-consent-and-payout-release: due/consented, no open claim, approved payment, enabled account; 10% commission. | `test_bb_claims_payouts.py::test_payout_eligibility_and_idempotence` | 6 | 0 | 0 | 0 |
| README.md#setup; odd/tasks/caja-negra.md S2: real uvicorn serves health and OpenAPI. | `test_bb_harness.py::test_real_http_health_and_schema` | 1 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S2: locally signed Supabase-shaped actors reach the real API. | `test_bb_harness.py::test_local_signed_actor` | 1 | 0 | 0 | 0 |
| OpenAPI InvitationCreate: email, length, additionalProperties=false; odd/tasks/caja-negra.md S3 invalid input. | `test_bb_invitations_shared_trips.py::test_invitation_validation` | 4 | 0 | 0 | 0 |
| OpenAPI company/profiles/me driver-invitations; odd/tasks/caja-negra.md S3 wrong-role decision table. | `test_bb_invitations_shared_trips.py::test_invitation_company_owner_only` | 2 | 0 | 0 | 0 |
| OpenAPI InvitationAccept: URL-safe token 32..128 chars and no unknown fields. | `test_bb_invitations_shared_trips.py::test_invitation_accept_token_validation` | 4 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3 owner/non-owner IDOR; OpenAPI InvitationList and revoke operation. | `test_bb_invitations_shared_trips.py::test_invitation_lists_are_scoped` | 1 | 0 | 0 | 0 |
| README.md#shared-trips: publish paid shareable route, provider-only trip id, close keeps linked services. | `test_bb_invitations_shared_trips.py::test_publish_and_close_shared_trip` | 1 | 0 | 0 | 0 |
| README.md#shared-trips: requestedTripId requires acceptsSharing=true; omission also 422 with no writes. | `test_bb_invitations_shared_trips.py::test_join_requires_explicit_sharing` | 2 | 0 | 0 | 0 |
| README.md#shared-trips: wrong requested profile=404, closed trip=409, no join written. | `test_bb_invitations_shared_trips.py::test_join_trip_profile_and_closed_guards` | 1 | 0 | 0 | 0 |
| README.md#shared-trips; odd/tasks/viajes-compartidos.md S2: paid join links stops, separate customer chat/payment. | `test_bb_invitations_shared_trips.py::test_second_customer_paid_join_keeps_chats_and_services_separate` | 1 | 0 | 0 | 0 |
| odd/tasks/viajes-compartidos.md S1: sharing defaults to not accepted, stored exclusive. | `test_bb_invitations_shared_trips.py::test_default_request_is_exclusive` | 1 | 0 | 0 | 0 |
| README.md#shared-trips: exclusive service refuses publication with 409 and unchanged rows. | `test_bb_invitations_shared_trips.py::test_exclusive_service_cannot_publish_trip` | 1 | 0 | 0 | 0 |
| README.md#shared-trips: service that already has a trip refuses a duplicate publication with 409. | `test_bb_invitations_shared_trips.py::test_duplicate_publication_does_not_duplicate_trip` | 1 | 0 | 0 | 0 |
| README.md#payments-simulated-provider; odd/tasks/caja-negra.md S3: approval reserves once, pay twice refused. | `test_bb_payments.py::test_payment_creates_exactly_one_service` | 1 | 0 | 0 | 0 |
| README.md#payments-simulated-provider: only the paying customer may consume a checkout link. | `test_bb_payments.py::test_checkout_is_bound_to_paying_customer` | 2 | 0 | 0 | 0 |
| README.md#payments-simulated-provider: signed checkout, refused confirmation releases consumption. | `test_bb_payments.py::test_tampered_checkout_does_not_consume_link` | 1 | 0 | 0 | 0 |
| README.md#payments-simulated-provider: webhook requires secret (401); simulated provider refused (403). | `test_bb_payments.py::test_webhook_cannot_approve_simulated_payment` | 3 | 0 | 0 | 0 |
| README.md#payments-simulated-provider: checkout link is single-use; odd/tasks/caja-negra.md S3 pay twice. | `test_bb_payments.py::test_consumed_checkout_link_is_rejected` | 0 | 0 | 1 | 0 |
| odd/tasks/panel-proveedores.md S3; README.md#provider-vehicles-private-supabase-storage-bucket: owner only. | `test_bb_provider_profile_vehicles.py::test_provider_owner_only_routes` | 2 | 0 | 0 | 0 |
| odd/tasks/panel-proveedores.md S3: incomplete PUT auto-unpublishes; publish saves visibility only when complete. | `test_bb_provider_profile_vehicles.py::test_profile_draft_publish_and_unpublish` | 1 | 0 | 0 | 0 |
| odd/tasks/panel-proveedores.md S3: required keys, unknown communes/types and strict OpenAPI ProviderProfileUpdate. | `test_bb_provider_profile_vehicles.py::test_profile_invalid_save_has_no_write` | 4 | 0 | 0 | 0 |
| README.md#provider-vehicles-private-supabase-storage-bucket: year 1886..2200, weight above zero. | `test_bb_provider_profile_vehicles.py::test_vehicle_numeric_boundaries` | 6 | 0 | 0 | 0 |
| README.md#provider-vehicles-private-supabase-storage-bucket: byte-detected photo, chat 5 MiB size cap. | `test_bb_provider_profile_vehicles.py::test_vehicle_file_boundaries` | 3 | 0 | 0 | 0 |
| README.md#provider-vehicles-private-supabase-storage-bucket: normalized plate unique, foreign vehicle same 404. | `test_bb_provider_profile_vehicles.py::test_vehicle_duplicate_and_idor_delete` | 1 | 0 | 0 | 0 |
| README.md#provider-vehicles-private-supabase-storage-bucket: referenced vehicle deletion returns 409. | `test_bb_provider_profile_vehicles.py::test_assigned_vehicle_cannot_be_deleted` | 1 | 0 | 0 | 0 |
| README.md#request-images-private-supabase-storage-bucket; OpenAPI POST images (201): MIME bytes, 5 MiB, owner-only image upload. | `test_bb_provider_profile_vehicles.py::test_request_image_file_boundaries` | 3 | 0 | 0 | 0 |
| README.md#request-images-private-supabase-storage-bucket: max five, sixth 409, read owner/provider only. | `test_bb_provider_profile_vehicles.py::test_request_image_count_and_visibility` | 1 | 0 | 0 | 0 |
| README.md#request-images-private-supabase-storage-bucket: JPEG/PNG/WebP determined by bytes, not MIME. | `test_bb_provider_profile_vehicles.py::test_documented_image_type_partitions` | 3 | 0 | 0 | 0 |
| README.md#public-browse-api; OpenAPI query bounds: pages 1..50, offsets 0..5000. | `test_bb_public_browse.py::test_page_boundaries` | 14 | 0 | 0 | 0 |
| README.md#public-browse-api; OpenAPI /api/services: q<=120, CUT digit lengths. | `test_bb_public_browse.py::test_service_filter_boundaries` | 9 | 0 | 0 | 0 |
| README.md#public-browse-api; OpenAPI /api/shared-routes: five-digit CUT codes. | `test_bb_public_browse.py::test_route_commune_boundaries` | 8 | 0 | 0 | 0 |
| README.md#public-browse-api: departure filters require timezone-aware ISO-8601. | `test_bb_public_browse.py::test_route_datetime_partitions` | 6 | 0 | 0 | 0 |
| README.md#public-browse-api and #hidden-service-types: public DTOs omit private fields. | `test_bb_public_browse.py::test_catalog_visibility_and_privacy` | 1 | 0 | 0 | 0 |
| OpenAPI /api/providers/{profile_id}: UUID; odd/tasks/panel-proveedores.md S3: unpublished absent. | `test_bb_public_browse.py::test_provider_identifier_partitions` | 2 | 0 | 0 | 0 |
| README.md#public-browse-api; OpenAPI LocationCatalog: official CUT region/commune codes. | `test_bb_public_browse.py::test_locations_catalog` | 1 | 0 | 0 | 0 |
| OpenAPI ServiceRequestCreate: required addresses, CUT, UUID, nonnegative cargo, strict fields. | `test_bb_requests_quotations.py::test_request_validation_has_no_writes` | 9 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3: wrong-role authorization table; OpenAPI customer service request operation. | `test_bb_requests_quotations.py::test_only_customer_creates_request` | 2 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3 request→quotation lifecycle and owner/non-owner IDOR; OpenAPI request decisions. | `test_bb_requests_quotations.py::test_request_acceptance_and_scoping` | 1 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3 state transitions; duplicate-request policy is unspecified; OpenAPI request reject operation. | `test_bb_requests_quotations.py::test_rejected_request_never_creates_chat` | 1 | 0 | 0 | 0 |
| OpenAPI QuotationCreate: positive integer CLP, validity 1..168, description 1..1000. | `test_bb_requests_quotations.py::test_quotation_boundaries` | 10 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3 provider quotation/customer payment and participant IDOR decision table. | `test_bb_requests_quotations.py::test_quotation_actor_table` | 3 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3: reject quotation then payment must be rejected, with no reservation. | `test_bb_requests_quotations.py::test_quotation_reject_then_pay_is_refused` | 1 | 0 | 0 | 0 |
| OpenAPI /api/quotations/{quotation_id}/reject UUID; odd/tasks/caja-negra.md S3 unknown-ID partition. | `test_bb_requests_quotations.py::test_unknown_quotation` | 2 | 0 | 0 | 0 |
| README.md#contracted-services: owner/assigned driver/customer visibility, 404 for hidden service. | `test_bb_services_lifecycle.py::test_service_visibility` | 5 | 0 | 0 | 0 |
| OpenAPI ServiceAssignmentsUpdate/ServiceAssignmentPair: nonempty UUID pairs, no extra fields. | `test_bb_services_lifecycle.py::test_assignment_body_validation` | 4 | 0 | 0 | 0 |
| README.md#live-service-location-in-progress-services: invalid/missing position gives 422, stays confirmed. | `test_bb_services_lifecycle.py::test_start_requires_valid_location_without_transition` | 7 | 0 | 0 | 0 |
| README.md#live-service-location-in-progress-services: inclusive GPS bounds, driver-only writes, owner/customer reads. | `test_bb_services_lifecycle.py::test_live_location_boundaries_and_authorization` | 3 | 0 | 0 | 0 |
| odd/tasks/caja-negra.md S3: completing before start is an invalid transition. | `test_bb_services_lifecycle.py::test_complete_before_start_is_refused` | 1 | 0 | 0 | 0 |
| README.md#delivery-photos-private-supabase-storage-bucket: 8 MiB cap; PNG detected from bytes. | `test_bb_services_lifecycle.py::test_delivery_file_boundaries` | 4 | 0 | 0 | 0 |
| README.md#live-service-location-in-progress-services and #delivery-photos-private-supabase-storage-bucket. | `test_bb_services_lifecycle.py::test_completion_deletes_live_position_and_exposes_private_photo` | 1 | 0 | 0 | 0 |

### Trazabilidad de los entregables S1–S7

| Especificación | Evidencia | Estado |
|---|---|---|
| S1 | Fuentes en cada docstring, API OpenAPI servida; ningún cambio en fuentes productivas | Cumplida para los escenarios enumerados; ambigüedades en sección 9 |
| S2 | `conftest.py`, `test_bb_harness.py`, rechazo de puerto prohibido, escenarios con datos persistidos | Arnés operativo; la condición de suite predeterminada verde no puede afirmarse por D2 preexistente |
| S3 | Tablas de técnicas y matriz; cadena de negocio HTTP y desembolsos locales | Técnicas aplicadas; límites no ejercitados indicados en sección 10 |
| S4 | Nueve módulos por área y matriz de resultados | Entregada la estructura exigida; no equivale a cobertura exhaustiva del contrato |
| S5 | Reporte JSON Playwright, tabla por archivo y lista de brechas | 427 aprobadas; sin nuevas pruebas Playwright |
| S6 | D1 con `xfail(strict=True, reason="BUG: ...")`; ninguna corrección productiva | Defecto reproducible conservado; D2 es un fallo heredado fuera del directorio autorizado |
| S7 | Este documento, con resultados medidos y limitaciones explícitas | Informe entregado |

## 8. Defectos y evidencia reproducible

### D1 — Un enlace de checkout consumido vuelve a devolver aprobación

- **Severidad: media, discrepancia contractual.** El comportamiento observado no produjo doble servicio ni demostró un segundo cargo. No se clasifica como duplicación monetaria ni como acceso de otro cliente.
- **Fuente:** `backend/README.md#payments-simulated-provider`: el enlace está ligado al pago y al cliente, vence a los quince minutos y es de un solo uso. `odd/tasks/caja-negra.md S3` pide rechazar transiciones inválidas como pagar dos veces.
- **Precondiciones:** solicitud aceptada, cotización pendiente, checkout creado y completado satisfactoriamente por su cliente.
- **Reproducción:** repetir el mismo POST y el mismo token después de la primera aprobación.

```http
POST /api/payments/simulated/<paymentId>/complete
Authorization: Bearer <JWT local del cliente propietario>
Content-Type: application/json

{"token":"<token del checkout ya consumido>","approve":true}
```

Respuesta observada, con identificadores sintéticos normalizados para facilitar la lectura:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"paymentId":"<paymentId>","status":"approved","quotationId":"<quotationId>","quotationStatus":"paid","serviceId":"<mismo serviceId de la primera aprobación>"}
```

**Esperado:** rechazo de reutilización del enlace consumido, sin fijar un código concreto que el README no especifica. **Persistencia observada:** sigue existiendo un único `Servicio`.

Prueba permanente:

```bash
cd backend
AMIRA_BLACKBOX_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres uv run pytest tests/blackbox/test_bb_payments.py::test_consumed_checkout_link_is_rejected -v
```

Está marcada `xfail(strict=True)` con motivo `BUG:`. Un cambio que haga pasar esa aserción producirá XPASS estricto hasta retirar la marca de forma autorizada. La aserción de creación válida y unicidad del servicio permanece en una prueba separada aprobada.

**Recomendación:** decidir si la intención del enlace es rechazo estricto tras consumo o respuesta idempotente. La idempotencia del webhook también está documentada, pero no debe confundirse automáticamente con autorización para reutilizar el enlace del navegador. Alinear documentación y comportamiento en una tarea distinta.

### D2 — Fallo heredado de la suite predeterminada por fecha fija vencida

- **Severidad: baja para producto, relevante para la señal de pruebas.** No demuestra un fallo productivo nuevo; impide declarar verde la suite predeterminada.
- **Prueba:** `tests/test_public_provider_routes.py::test_quote_request_uses_server_account_actor_and_creates_only_request`.
- **Dato existente:** `requestedAt="2026-11-08T10:00:00-03:00"`, anterior a la fecha de esta ejecución.
- **Respuesta observada:** 422; la prueba espera 201.
- **Referencia:** campaña `caja-negra.md S2` (preservar la suite predeterminada) y regla de fechas relativas de la campaña. La atribución a una fecha obsoleta es el diagnóstico sustentado por ese dato y el rechazo; no se alteró el reloj para demostrar causalidad adicional.
- **Reproducción:** `cd backend && uv run pytest tests/test_public_provider_routes.py::test_quote_request_uses_server_account_actor_and_creates_only_request -q`.
- **Control de referencia:** `uv run pytest --ignore=tests/blackbox -q` reproduce exactamente ese fallo: 856 aprobadas, 1 fallida, 3 omitidas en 11,86 s. La corrida predeterminada final agrega únicamente las 196 omisiones de caja negra: 856 aprobadas, 1 fallida, 199 omitidas en 11,82 s.
- **Tratamiento:** no se modificó ni se marcó la prueba heredada, porque su archivo no pertenece a la superficie autorizada. Se recomienda autorizar por separado el reemplazo de la fecha fija por una fecha futura relativa.

### Expectativas iniciales descartadas, no defectos

Las primeras ejecuciones de desarrollo detectaron supuestos incorrectos de las pruebas nuevas. Se contrastaron con el OpenAPI servido y el README: el POST de imágenes devuelve 201, la revocación de invitación devuelve 200 y la lectura de imágenes por otro cliente sigue la política de la ruta del proveedor (403), mientras que la carga ajena tiene 404 explícito. Esos supuestos se corrigieron en las pruebas; no se conservaron como supuestos fallos productivos ni se relajaron por lectura de implementación.

## 9. Ambigüedades y documentación desactualizada

| ID | Fuente | Incertidumbre y tratamiento |
|---|---|---|
| A1 | `PROJECT_OVERVIEW.md`, tecnología y estado inicial de `backend/README.md` | Describen documentación o un starter sin marketplace, mientras el contrato servido expone operaciones funcionales. Se utilizaron las secciones funcionales y el OpenAPI para los casos concretos; se recomienda actualizar esos resúmenes históricos. |
| A2 | README de pagos | Conviven la afirmación de enlace de un solo uso y confirmaciones idempotentes. El alcance exacto del replay del navegador debe aclararse; D1 registra la discrepancia sin atribuir duplicación monetaria. |
| A3 | OpenAPI de autenticación y operaciones protegidas | No enumera todos los errores de autenticación/negocio: muchas operaciones solo publican éxito y 422. Se comprueba rechazo de credenciales inválidas sin inventar equivalencia entre todos los códigos 401/403. |
| A4 | OpenAPI de decisiones de solicitudes y `caja-negra.md S3` | No define en las fuentes autorizadas el resultado exacto de repetir aceptar/rechazar una solicitud. Se retiró la expectativa específica de replay de decisiones; no se convirtió una preferencia del ejecutor en un requisito. |
| A5 | README de Storage | La precedencia entre configuración ausente, autorización y validación de archivos no queda completamente definida para todas las rutas. La campaña habilitó un doble local para medir las validaciones, sin inferir que esos mismos errores precedan a un 503 en cualquier entorno. |
| A6 | OpenAPI y README de listas | Los límites formales están claros, pero no se fija una política de normalización completa para toda consulta textual, el orden entre registros empatados ni todos los códigos de recurso desconocido. No se afirma haber cerrado esos vacíos. |

## 10. Qué no se probó y por qué

- **Supabase, correo, pagos o despliegues alojados:** expresamente fuera del alcance de red autorizado. No se contactaron servicios alojados ni se configuraron sus credenciales para el arnés.
- **Autenticación Supabase real, SMS, Didit, renovación/revocación real de sesiones y entrega de correo:** se usaron identidades firmadas por JWKS local. La tabla valida decisiones de JWT, no la operación de proveedores externos. La creación válida y reemisión de invitaciones con entrega efectiva no se probaron.
- **Storage real y compensación ante fallos:** el doble registra cargas y simula firma/eliminación; no prueba RLS de buckets, expiración efectiva, lectura del objeto firmado, borrado remoto ni recuperación ante caídas. Las muestras de tamaño máximo usan encabezados de imagen y relleno para medir límites y detección, no para certificar que un decodificador multimedia acepte imágenes arbitrarias.
- **Carreras, bloqueo real bajo competencia y carga:** los escenarios son secuenciales. El uso de una base real no demuestra ausencia de carreras en pagos, cupos de imágenes, viajes, reclamos o desembolsos concurrentes.
- **SSE completo:** se verificó autenticación, rechazo del token por URL y estado inicial del stream. No se midieron cinco conexiones simultáneas más una sexta, cierre por expiración del JWT, keepalive de veinte segundos, reconexión de LISTEN ni entrega entre procesos bajo fallos.
- **Tiempo real de reglas comerciales:** no se esperaron quince minutos de checkout ni veinticuatro horas de reclamos. La ventana de reclamos/desembolsos se preparó con SQL y el JWT vencido se generó expresamente. No se atribuye cobertura de expiración del checkout.
- **Todas las combinaciones comerciales:** no se ejercitaron todos los filtros de bandeja, empates de paginación, vencimiento/sustitución de cotizaciones, conflictos de asignación del mismo día, matrices completas de afiliación de conductor, todos los estados de alta de cuenta de desembolso, ni fallos del adaptador de desembolso. El importe neto se comprobó para bruto 10001 y comisión 10%; no se afirma cobertura exhaustiva de redondeos límite.
- **Entornos y navegadores adicionales:** solo el proyecto Chromium existente. No se midieron Firefox, WebKit, dispositivos físicos, GPS real, geolocalización en segundo plano ni accesibilidad exhaustiva.
- **Reembolsos, resolución de reclamos y dinero real:** fuera del contrato operativo actual; los adaptadores usados son simulados.
- **Cobertura estructural:** no se instrumentaron líneas ni ramas. El número de pruebas no constituye un porcentaje de cobertura funcional ni prueba de preparación para producción.

## 11. Recomendaciones priorizadas

1. Resolver la intención contractual de D1 y, en una tarea autorizada, alinear enlace consumido y comportamiento de replay sin perder idempotencia ni unicidad del servicio.
2. Corregir separadamente D2 para recuperar la señal de la suite predeterminada, usando una fecha relativa y conservando la validación de fechas reales.
3. Documentar errores de negocio/autorización y política de repetición en OpenAPI o en especificaciones vigentes; actualizar los resúmenes históricos de estado de proyecto.
4. Mantener esta suite como campaña optativa y destructiva sobre una base exclusiva. No reutilizar `AMIRA_TEST_DATABASE_URL` ni una instancia de desarrollo para habilitarla.
5. Planificar pruebas de competencia y fallos de adaptadores, además de un recorrido de navegador con persistencia real que una los fragmentos ya cubiertos por respuestas falsas.
6. Antes de cualquier habilitación real, verificar proveedores de identidad, correo, Storage, cobro y desembolso en un entorno autorizado, con políticas y secretos propios. Esta campaña local no autoriza esa actividad remota ni reemplaza su validación.

## 12. Conclusión

La evidencia local confirma los escenarios enumerados de límites, autorización, persistencia y transiciones comerciales sobre la aplicación real. Existe una discrepancia contractual reproducible de checkout conservada como fallo esperado estricto. Playwright completó su campaña existente sin fallos, pero utiliza dobles y no demuestra la integración completa con el backend real.

La suite predeterminada continúa con un fallo heredado reproducible, de modo que **no se declara que todo el repositorio esté verde**. La entrega consiste en pruebas, aislamiento, trazabilidad y este informe; no en correcciones productivas ni certificación de producción. Los commits y sus verificaciones están registrados en [la tabla de tareas y su bitácora](../../odd/tasks/caja-negra.md).
