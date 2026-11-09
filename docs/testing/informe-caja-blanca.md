# Informe de pruebas de caja blanca

## Resumen ejecutivo

La campaña elevó la cobertura combinada del backend de **92,43 % a 99,65 %** sin modificar código de producción. La medición final es **99,78 % de sentencias** y **99,00 % de ramas**: 4038 de 4047 sentencias y 796 de 804 ramas ejecutadas. La suite final obtuvo **1071 pruebas aprobadas, 3 omitidas y 1 fallo esperado estricto**.

En el frontend, el comando completo pasó de **88,91 % a 97,77 % de líneas**, de **96,15 % a 98,96 % de ramas** y de **83,78 % a 99,12 % de funciones**. El ámbito solicitado de lógica de `src/lib`, excluyendo únicamente el cableado del SDK de navegador `supabase/client.ts`, alcanzó **100 % de líneas, 99,35 % de ramas y 100 % de funciones**. Todos sus módulos alcanzan al menos 95 % de líneas y ramas.

Se corrigió un defecto temporal de las pruebas y se reprodujeron **dos defectos de producción**, conservados como `xfail(strict=True)` y `test.todo`, sin corregir producción. La cobertura alta no equivale a ausencia de defectos: ambos fallos esperados ejecutan precisamente las líneas cuyo comportamiento es incorrecto.

## 1. Objetivo y alcance

El objetivo fue ejecutar S1–S7 de `odd/tasks/caja-blanca.md`: instalar medición de cobertura, estabilizar fechas, aumentar cobertura de decisiones y errores, y documentar resultados verificables. El trabajo se realizó en `test/caja-blanca`, sin cambio de rama ni publicación remota. El punto inicial fue `72f7395b7d88dd2833882b144adec27cd6dc134e`.

Ámbitos autorizados: pruebas del backend, pruebas unitarias del frontend, configuración de cobertura y dependencias de desarrollo del backend, comandos de ambos README, registro de tareas e informe. La comprobación `git diff 72f7395 -- backend/src frontend/src` no mostró cambios de producción. Tampoco se alteraron pruebas E2E, CI, infraestructura ni configuración de aplicaciones.

La prioridad fue observar comportamiento público: respuestas y rechazos de handlers, funciones públicas de servicio, estado de pagos/cotizaciones/servicios, commits y rollbacks, llamadas de almacenamiento y argumentos enviados a `fetch`. Se reutilizaron `FakeSession`, resultados simulados y fixtures SQLite existentes. Se sustituyeron adaptadores de red; no se realizaron llamadas reales a Supabase, JWKS, correo, almacenamiento o bases alojadas.

### Cumplimiento por especificación

| Especificación | Resultado y límites |
|---|---|
| S1: herramientas | `pytest-cov` en el grupo `dev`, lock actualizado y validado; configuración de ramas y líneas faltantes; comandos documentados en ambos README. |
| S2: fechas | Fallo 422/201 reproducido y corregido con reloj de validación fijo para los fixtures históricos de solicitudes. Se revisaron fechas en ambos árboles de pruebas. Fechas E2E fuera de las superficies autorizadas permanecen como riesgo identificado. |
| S3: módulos críticos | Autenticación, base de datos, desembolsos, viajes compartidos y simulador alcanzan 100 % de líneas y ramas. Las excepciones de pagos y entrada CLI se detallan por línea en la sección 8. |
| S4: cuentas e invitaciones | Ramas: `account_routes` 96,97 %, `account_schemas` 100 %, `invitation_routes` 96,34 % y `fallback_routes` 100 %. |
| S5: resto del backend | Todos los módulos enumerados por S5 alcanzan al menos 95 % de ramas; la mayoría alcanzan 100 %. |
| S6: lógica del frontend | Todos los módulos incluidos superan 95 % en líneas y ramas. La exclusión del SDK se muestra sin retirarla del resultado bruto. |
| S7: informe | Comparativas por módulo, técnicas, comandos, nuevas pruebas, defectos, exclusiones y recomendaciones en este documento. |

## 2. Técnicas de caja blanca aplicadas

### Cobertura de sentencias

Se partió de los huecos de `--cov-report=term-missing`, se inspeccionaron las condiciones que los protegían y se construyeron entradas que alcanzaran esas sentencias. Ejemplos: configuración incompleta, rechazo de credenciales, fallos de firmado de URL y excepciones durante commit. La comparación usa el mismo conjunto de 50 archivos del backend, con 4047 sentencias y 804 ramas antes y después.

### Cobertura de ramas y decisiones

Se observaron ambos destinos de decisiones relevantes: existencia o ausencia de cuenta; perfil propio o ajeno; sesión válida o insuficiente; solicitud pendiente o inconsistente; almacenamiento disponible o fallido; actualización atómica aplicada o perdida; y suscripción activa, saturada o expirada. En S4 y S5 se comprobó el porcentaje específico de ramas, no solo el porcentaje combinado redondeado de terminal.

### Cobertura de caminos

Se ejercitaron caminos completos y acotados: verificación de identidad → consulta → rechazo sin escritura; carga de objeto → error de persistencia → rollback y eliminación compensatoria; pago aprobado → conflicto de integridad → rollback sin servicio; y envío de código → activación perdida → rollback. No se afirma cobertura exhaustiva de todos los caminos: bucles, estados y combinaciones hacen que ese objetivo sea distinto de cubrir decisiones.

### Cobertura de condiciones

La parametrización varió individualmente cada campo de cuentas recuperadas, los datos de perfil y conductor, las respuestas del verificador de correo y las causas de rechazo de sesión. Esto permite detectar cortocircuitos y campos omitidos. No se aplicó instrumentación específica de MC/DC ni se declara cobertura MC/DC completa. Los porcentajes de ramas no son una medida independiente de cobertura de condiciones.

### Errores y valores límite

Se incluyeron entradas vacías y configuración inválida; límites de tamaño de imagen y payload `NOTIFY`; tasa máxima de invitaciones; agotamiento de intentos; tokens vacíos; proveedor de autenticación o almacenamiento fallido; resultados atómicos nulos; vencimiento de stream en el límite de timeout; delimitadores SSE sin dos puntos y CR dividido; coordenadas inválidas y códigos de error geográfico. No se utilizaron esperas temporizadas nuevas: el control asíncrono usa eventos, colas y cancelación explícita.

## 3. Herramientas, entorno y comandos

Mediciones realizadas el **9 de noviembre de 2026**, con Python **3.12.15**, uv **0.13.1**, Node.js **26.12.0**, `pytest-cov` **7.1.0** y coverage.py **7.17.2**. Se conservó el estilo de fixtures y los runners existentes.

### Backend

Desde la raíz del repositorio:

```bash
cd backend
uv add --group dev pytest-cov
uv lock --check
uv run pytest --cov=amira_api --cov-branch --cov-report=term-missing
```

La instalación se realizó con aprobación para acceso a la caché y descarga de dependencias. `uv lock --check` terminó correctamente. La configuración añadida es:

```toml
[tool.coverage.run]
source = ["amira_api"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = true
```

Para obtener números exactos, las ejecuciones de medición añadieron al mismo comando `--cov-report=json:/tmp/amira-baseline.json`, `--cov-report=json:/tmp/amira-t1.json` hasta `--cov-report=json:/tmp/amira-t4.json`, y `--cov-report=json:/tmp/amira-final.json`. Los JSON son evidencia temporal de la sesión; las tablas de este informe preservan sus valores, no dependen de que `/tmp` sobreviva.

Pruebas enfocadas ejecutadas antes de cada suite completa:

```bash
uv run pytest tests/test_public_provider_routes.py tests/test_shared_trip_routes.py tests/test_validation_messages.py -q
uv run pytest tests/test_whitebox_critical.py tests/test_whitebox_money.py -q
uv run pytest tests/test_whitebox_accounts.py tests/test_whitebox_invitations.py tests/test_whitebox_fallback.py -q
uv run pytest tests/test_whitebox_storage_routes.py tests/test_whitebox_route_guards.py tests/test_whitebox_realtime.py -q
uv run pytest tests/test_whitebox_invitations.py tests/test_chat_unread.py -q
```

La última ejecución enfocada corresponde a la auditoría final de determinismo: fija también el reloj de las nuevas pruebas de invitaciones y su fixture reutilizado, y el reloj SQLite del caso de lectura que comparaba contra 2030. No se cambió la lógica productiva de expiración.

### Frontend

Desde `frontend`:

```bash
node --test tests/unit/whitebox-access.node-test.mjs tests/unit/whitebox-pure.node-test.mjs
node --test --experimental-test-coverage tests/unit/*.mjs
node tests/unit/whitebox-access.node-test.mjs
node tests/unit/whitebox-pure.node-test.mjs
```

Se ejecutó además el runner con un reporter temporal que captura el evento nativo `test:coverage`:

```bash
node --test --experimental-test-coverage --test-reporter=/tmp/amira-coverage-reporter.mjs tests/unit/*.mjs
```

El reporter solo serializa `event.data.summary`; no altera archivos de producción ni los cálculos de V8. Se recogieron JSON antes de añadir las pruebas del frontend y después. El comando normal informa **19 archivos aprobados en el punto inicial y 22 al final**; el total final incluye el loader de pruebas. En este entorno el resumen del proceso padre es por archivo, por lo que no debe presentarse como el número total de aserciones individuales. La ejecución directa de los archivos nuevos informa **26 pruebas aprobadas y 1 TODO ejecutado** en acceso/API, y **9 aprobadas** en lógica pura.

## 4. Resultados y comparación global

| Medida | Inicial | Final |
|---|---:|---:|
| Backend: sentencias totales | 4047 | 4047 |
| Backend: sentencias sin ejecutar | 243 | 9 |
| Backend: cobertura de sentencias | 94,00 % | 99,78 % |
| Backend: ramas totales | 804 | 804 |
| Backend: ramas ejecutadas | 680 | 796 |
| Backend: cobertura de ramas | 84,58 % | 99,00 % |
| Backend: ramas parciales | 98 | 8 |
| Backend: cobertura combinada | 92,43 % | 99,65 % |
| Backend: aprobadas / fallidas / omitidas / xfail | 856 / 1 / 3 / 0 | 1071 / 0 / 3 / 1 |
| Frontend: líneas, resultado bruto del runner | 88,91 % | 97,77 % |
| Frontend: ramas, resultado bruto del runner | 96,15 % | 98,96 % |
| Frontend: funciones, resultado bruto del runner | 83,78 % | 99,12 % |
| Frontend: líneas de lógica pura `src/lib` | 1037/1143 = 90,73 % | 1143/1143 = 100 % |
| Frontend: ramas de lógica pura `src/lib` | 387/401 = 96,51 % | 456/459 = 99,35 % |
| Frontend: funciones de lógica pura `src/lib` | 91/108 = 84,26 % | 109/109 = 100 % |

El 92 % y los conteos del backend registrados en L3 se reprodujeron antes de los cambios. La diferencia entre 92 % de terminal y 92,43 % en la tabla es precisión de presentación, no una baseline diferente.

**Precaución sobre denominadores del frontend:** V8 descubre más bloques y funciones al ejecutar caminos antes no invocados. Por eso las ramas de lógica pura pasan de 401 a 459 aunque el código de producción sea idéntico. El incremento no representa una modificación de lógica ni permite comparar porcentajes como si el denominador fuera fijo. El resultado bruto también incluye loaders de pruebas, a diferencia del ámbito puro.

### Secuencia de verificación

| Tarea | Enfocadas | Suite completa observada |
|---|---|---|
| T1 | 78 aprobadas tras estabilizar el reloj | 857 aprobadas, 3 omitidas; 92,43 % combinado. |
| T2 | 44 aprobadas, 1 xfail estricto | 901 aprobadas, 3 omitidas, 1 xfail; 93,82 % combinado. |
| T3 | 118 aprobadas | 1019 aprobadas, 3 omitidas, 1 xfail; objetivos S4 satisfechos. |
| T4 | 52 aprobadas | 1071 aprobadas, 3 omitidas, 1 xfail; 99,65 % combinado. |
| T5 | 2 archivos aprobados; 35 casos nuevos aprobados y 1 TODO al ejecutarlos directamente | 22 archivos aprobados; 97,77 % líneas / 98,96 % ramas brutas. |
| T6 | 68 casos de invitaciones y lectura aprobados tras fijar sus relojes; lectura estructural del informe | Backend: 1071 aprobadas, 3 omitidas, 1 xfail. Frontend: 22 archivos aprobados. |

Los fallos intermedios de construcción de pruebas se corrigieron antes del commit correspondiente. Se observó y corrigió expresamente un hueco de verificación de T4: el cierre `STREAM_CLOSED` no estaba cubierto pese al buen porcentaje combinado; su prueba adicional elevó `realtime_routes` a 100 % de ramas. Se dejó constancia en el Log.

## 5. Cobertura del backend por módulo

Todas las rutas de esta tabla son relativas a `backend/src/amira_api/`. Cada celda con flecha representa **inicial → final**. `Stmts` es el número de sentencias; `Miss`, las sentencias no ejecutadas; `Branch`, los destinos de ramas; `BrPart`, las ramas parciales; `Cover`, el porcentaje combinado de coverage.py. La última columna muestra el porcentaje específico de ramas final, que es el criterio de S4/S5. Las 25 líneas excluidas por reglas ya existentes permanecen sin cambios; no se añadieron exclusiones para elevar resultados.

| Módulo | Stmts | Miss | Branch | BrPart | Cover % | Ramas final % |
|---|---:|---:|---:|---:|---:|---:|
| `__init__.py` | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `account_routes.py` | 124 → 124 | 38 → 1 | 66 → 66 | 14 → 2 | 65.26 → 98.42 | 96.97 |
| `account_schemas.py` | 76 → 76 | 4 → 0 | 22 → 22 | 4 → 0 | 91.84 → 100.00 | 100.00 |
| `auth.py` | 102 → 102 | 10 → 0 | 32 → 32 | 6 → 0 | 88.06 → 100.00 | 100.00 |
| `chat_access.py` | 12 → 12 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `chat_routes.py` | 211 → 211 | 7 → 0 | 46 → 46 | 3 → 0 | 96.11 → 100.00 | 100.00 |
| `chat_schemas.py` | 59 → 59 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `clock.py` | 5 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `contact_filter.py` | 14 → 14 | 0 → 0 | 4 → 4 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `customer_routes.py` | 139 → 139 | 2 → 0 | 38 → 38 | 0 → 0 | 98.87 → 100.00 | 100.00 |
| `customer_schemas.py` | 33 → 33 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `db.py` | 34 → 34 | 11 → 0 | 8 → 8 | 3 → 0 | 61.90 → 100.00 | 100.00 |
| `evidence_storage.py` | 52 → 52 | 5 → 0 | 16 → 16 | 3 → 0 | 88.24 → 100.00 | 100.00 |
| `fallback_routes.py` | 126 → 126 | 16 → 0 | 30 → 30 | 5 → 0 | 86.54 → 100.00 | 100.00 |
| `invitation_routes.py` | 257 → 257 | 55 → 3 | 82 → 82 | 24 → 3 | 74.34 → 98.23 | 96.34 |
| `location_routes.py` | 29 → 29 | 0 → 0 | 8 → 8 | 1 → 0 | 97.30 → 100.00 | 100.00 |
| `location_schemas.py` | 13 → 13 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `main.py` | 53 → 53 | 7 → 0 | 2 → 2 | 0 → 0 | 83.64 → 100.00 | 100.00 |
| `models.py` | 464 → 464 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `payment_provider.py` | 8 → 8 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `payment_routes.py` | 118 → 118 | 1 → 1 | 32 → 32 | 2 → 1 | 98.00 → 98.67 | 96.88 |
| `payment_schemas.py` | 30 → 30 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `payment_service.py` | 97 → 97 | 10 → 1 | 30 → 30 | 3 → 1 | 89.76 → 98.43 | 96.67 |
| `payout_provider.py` | 17 → 17 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `payout_service.py` | 76 → 76 | 2 → 0 | 16 → 16 | 2 → 0 | 95.65 → 100.00 | 100.00 |
| `provider_profile_routes.py` | 74 → 74 | 0 → 0 | 24 → 24 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `provider_profile_schemas.py` | 36 → 36 | 0 → 0 | 6 → 6 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `provider_service_routes.py` | 250 → 250 | 3 → 0 | 64 → 64 | 1 → 0 | 98.73 → 100.00 | 100.00 |
| `provider_service_schemas.py` | 95 → 95 | 0 → 0 | 4 → 4 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `public_routes.py` | 216 → 216 | 9 → 0 | 74 → 74 | 6 → 0 | 94.83 → 100.00 | 100.00 |
| `public_schemas.py` | 154 → 154 | 0 → 0 | 4 → 4 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `quotation_routes.py` | 69 → 69 | 1 → 0 | 22 → 22 | 1 → 0 | 97.80 → 100.00 | 100.00 |
| `quotation_schemas.py` | 25 → 25 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `quotation_service.py` | 21 → 21 | 0 → 0 | 4 → 4 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `realtime.py` | 236 → 236 | 15 → 2 | 56 → 56 | 5 → 0 | 93.15 → 99.32 | 100.00 |
| `realtime_routes.py` | 67 → 67 | 4 → 0 | 12 → 12 | 1 → 0 | 93.67 → 100.00 | 100.00 |
| `release_payouts.py` | 29 → 29 | 7 → 1 | 4 → 4 | 2 → 1 | 72.73 → 93.94 | 75.00 |
| `request_image_routes.py` | 107 → 107 | 13 → 0 | 26 → 26 | 4 → 0 | 87.22 → 100.00 | 100.00 |
| `request_image_schemas.py` | 11 → 11 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `service_type_visibility.py` | 8 → 8 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `service_views.py` | 58 → 58 | 0 → 0 | 8 → 8 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `settings.py` | 61 → 61 | 0 → 0 | 8 → 8 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `shared_trip_routes.py` | 63 → 63 | 0 → 0 | 8 → 8 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `shared_trip_schemas.py` | 31 → 31 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `shared_trip_service.py` | 61 → 61 | 4 → 0 | 20 → 20 | 4 → 0 | 90.12 → 100.00 | 100.00 |
| `simulated_payment_provider.py` | 49 → 49 | 1 → 0 | 8 → 8 | 1 → 0 | 96.49 → 100.00 | 100.00 |
| `simulated_payout_provider.py` | 13 → 13 | 0 → 0 | 2 → 2 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `supabase_evidence_storage.py` | 29 → 29 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| `vehicle_routes.py` | 119 → 119 | 18 → 0 | 18 → 18 | 3 → 0 | 84.67 → 100.00 | 100.00 |
| `vehicle_schemas.py` | 16 → 16 | 0 → 0 | 0 → 0 | 0 → 0 | 100.00 → 100.00 | 100.00 |
| **TOTAL** | **4047 → 4047** | **243 → 9** | **804 → 804** | **98 → 8** | **92.43 → 99.65** | **99.00** |

## 6. Cobertura del frontend por módulo

Rutas relativas a `frontend/src/lib/`. Las celdas muestran **inicial → final**. Node/V8 informa líneas, ramas y funciones, **no sentencias Python ni BrPart**. Por tanto, `Stmts` y `BrPart` son **no aplicables** en este instrumento; no se inventaron equivalencias. `Miss` en esta tabla significa líneas no cubiertas y `Cover` significa cobertura de líneas. El número de líneas incluye líneas contabilizadas por V8, no necesariamente sentencias ejecutables de Python.

| Módulo | Líneas (no Stmts) | Miss | Branch | Cover líneas % | Ramas % | Funciones % |
|---|---:|---:|---:|---:|---:|---:|
| `account-role-labels.ts` | 14 → 14 | 0 → 0 | 6 → 6 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `auth/account-api.ts` | 45 → 45 | 36 → 0 | 1 → 17 | 20.00 → 100.00 | 100.00 → 100.00 | 0.00 → 100.00 |
| `auth/dev-mfa.ts` | 31 → 31 | 0 → 0 | 9 → 9 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `chat-attachments.ts` | 28 → 28 | 0 → 0 | 20 → 20 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `chat-events.ts` | 88 → 88 | 0 → 0 | 47 → 49 | 100.00 → 100.00 | 89.36 → 97.96 | 100.00 → 100.00 |
| `chat-notifications.ts` | 35 → 35 | 0 → 0 | 16 → 15 | 100.00 → 100.00 | 93.75 → 100.00 | 100.00 → 100.00 |
| `chat-quotations.ts` | 104 → 104 | 3 → 0 | 47 → 49 | 97.12 → 100.00 | 97.87 → 100.00 | 90.00 → 100.00 |
| `chat-unread.ts` | 29 → 29 | 0 → 0 | 15 → 15 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `chats.ts` | 202 → 202 | 11 → 0 | 39 → 44 | 94.55 → 100.00 | 97.44 → 100.00 | 81.25 → 100.00 |
| `customer-cache-policy.ts` | 10 → 10 | 0 → 0 | 5 → 5 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `customer-rating-errors.ts` | 44 → 44 | 0 → 0 | 19 → 19 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `customer-rating-validation.ts` | 28 → 28 | 0 → 0 | 10 → 10 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `customer-request-retry.ts` | 15 → 15 | 0 → 0 | 3 → 3 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `customer-services-pagination.ts` | 12 → 12 | 0 → 0 | 6 → 6 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `geolocation.ts` | 114 → 114 | 0 → 0 | 47 → 47 | 100.00 → 100.00 | 95.74 → 100.00 | 100.00 → 100.00 |
| `post-login-path.ts` | 38 → 38 | 2 → 0 | 21 → 21 | 94.74 → 100.00 | 90.48 → 100.00 | 100.00 → 100.00 |
| `provider-nav-cache.ts` | 22 → 22 | 0 → 0 | 4 → 4 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `provider-profile-api.ts` | 153 → 153 | 30 → 0 | 40 → 48 | 80.39 → 100.00 | 95.00 → 95.83 | 64.29 → 100.00 |
| `provider-request-access.ts` | 56 → 56 | 24 → 0 | 9 → 35 | 57.14 → 100.00 | 100.00 → 100.00 | 42.86 → 100.00 |
| `provider-requests.ts` | 75 → 75 | 0 → 0 | 37 → 37 | 100.00 → 100.00 | 100.00 → 100.00 | 100.00 → 100.00 |
| `supabase/client.ts` | 26 → 26 | 23 → 23 | 1 → 1 | 11.54 → 11.54 | 100.00 → 100.00 | 0.00 → 0.00 |

El resultado final bruto comprende 1182/1209 líneas, 475/480 ramas y 112/113 funciones, incluidos los loaders y el SDK de navegador. Para todo `src/lib`, incluido el SDK, son 1146/1169 líneas y 457/460 ramas. La exclusión autorizada de `supabase/client.ts` solo se aplica al objetivo de lógica pura, no modifica el comando ni oculta la fila de baja cobertura.

## 7. Archivos nuevos y caminos comprobados

### Backend

| Archivo en `backend/tests/` | Comportamiento observado |
|---|---|
| `test_whitebox_critical.py` | Bearer ausente o vacío, claims inválidos, errores JWKS sin acceso real a red, prueba de fallback no consumible, claves cortas y sesiones nulas; normalización PostgreSQL y opciones de pool; generador de sesión y cierre; composición y CLI de desembolsos; secreto vacío; guardas de viaje compartido; servicio desaparecido bajo lock; reproducción estricta del defecto TLS. |
| `test_whitebox_money.py` | Chat ya liquidado, confirmación sin proveedor asignado, fallo de integridad con rollback y ausencia de servicio, cuenta desconocida y conflicto al incorporar una solicitud a viaje; se verifican estados de pago y número de servicios persistidos. |
| `test_whitebox_accounts.py` | Lectura de cuenta presente/ausente, cada dato privado incompatible, completar campos heredados, roles ausentes, recuperación tras inserciones concurrentes de usuario/perfil/conductor y validación de capacidades; se comprueban commits y rollbacks. |
| `test_whitebox_invitations.py` | Construcción de adaptadores, respuestas y excepciones de transporte, dominios de correo inválidos, estados de ciclo de vida, revocación y reemisión, identidad o dependencias ausentes, conversión de conductor independiente a empresa, configuración/tasa/impuestos y fallos de envío. Reloj final fijo para los fixtures nuevos. |
| `test_whitebox_fallback.py` | Sender no configurado, adquisición y liberación del lock PostgreSQL mediante conexión simulada, excepción de envío, activación perdida, agotamiento de intentos y consumo atómico perdido; se verifican códigos y transacciones. |
| `test_whitebox_storage_routes.py` | Resolución diferida de buckets privados, constructor del adaptador sin red, límites de tamaño, patente duplicada, errores de commit e integridad, eliminación compensatoria fallida, firmado fallido, propiedad perdida durante upload, lista vacía y rechazo de campos en blanco. |
| `test_whitebox_route_guards.py` | Cuenta desconocida, URLs de adjuntos y evidencia fallidas, estados de chat inconsistentes en aceptación/rechazo, rollback, asignación sin fecha y catálogo con regiones sin comunas. |
| `test_whitebox_realtime.py` | Límite de bytes `NOTIFY`, unsubscribe repetido, suscripción cerrada, URL inválida sin filtrar credenciales, heartbeat transaccional, lifespan con/sin listener, JWT sin expiración, recepción y retry tras error, creación de tarea, expiración durante timeout y descarte de stream por saturación. |

También se modificó `conftest.py` para aislar el reloj de validación de solicitudes únicamente en los módulos históricos afectados, y `test_chat_unread.py` para fijar `CURRENT_TIMESTAMP` en SQLite y evitar que el año 2030 deje de representar el futuro. El resto de las pruebas mantiene sus relojes y fixtures originales.

### Frontend

| Archivo en `frontend/tests/unit/` | Comportamiento observado |
|---|---|
| `whitebox-access.node-test.mjs` | Fallos de usuario, confirmación, MFA y sesión; token válido; propagación de error de assurance; mensajes públicos; URLs de API inseguras; opciones, Authorization y cache; lectura/guardado/publicación/despublicación del perfil; errores HTTP y JSON inválido; reproducción TODO de pérdida de `Headers`. |
| `whitebox-pure.node-test.mjs` | Detalles de errores de chat, acceso, límites de fecha relativa, fallback de estado, polling, normalización de redirección, fallo de parser URL simulado, delimitadores SSE, payloads incompatibles, previews inexistentes y errores de geolocalización. |
| `whitebox-client-loader.mjs` | Helper, no caso de negocio: sustituye exclusivamente `createClient` del cableado de navegador por un cliente controlado. Los módulos de acceso, API y lógica siguen siendo los reales. |

## 8. Líneas y ramas no cubiertas: justificación y seguimiento

### Backend: nueve sentencias y ocho destinos de ramas

| Archivo y línea/rama | Justificación y alcance de la excepción |
|---|---|
| `account_routes.py:194`, rama `193→194` | Guarda defensiva `company_driver_type is None` después de haber comprobado al inicio la existencia de esa misma configuración cuando `also_driver=True`. No es alcanzable con el flujo normal y los datos validados actuales. No se fabricó una mutación del payload durante la llamada para cubrirla. |
| `account_routes.py`, rama `190→219` | El bloque exterior solo admite `company_owner` o `independent_driver`; el primer caso de la cadena consume `independent_driver`, por lo que el `elif company_owner` no tiene un tercer estado válido. |
| `invitation_routes.py:290` | Entrega no configurada en creación de invitación. Permanecen pruebas de configuración de factories y de transporte; este rechazo concreto con sender ausente no se aisló en la ampliación. Es una brecha explícita, no prueba de comportamiento correcto. El módulo conserva 96,34 % de ramas. |
| `invitation_routes.py:343` | Entrega no configurada en reemisión. Misma limitación de aislamiento; se cubren reemisión válida, invitación ausente y ya aceptada. |
| `invitation_routes.py:369` | Verificador de correo ausente en aceptación. Se cubren construcción del verificador no configurado y rechazo de identidad, pero falta el handler con esta dependencia nula. |
| `payment_routes.py:60`, rama `59→60` | Falta el escenario específico de composición con entorno permitido y secreto o URL ausente. Hay cobertura de entorno denegado y construcción válida; el camino de configuración incompleta queda como excepción explícita a S3 y candidato inmediato a prueba adicional. No se presenta como 100 %. |
| `payment_service.py:175`, rama `174→175` | Publicación de eventos para otras cotizaciones pendientes. La creación pública de una nueva cotización ya reemplaza la anterior, por lo que los flujos normales no producen la colección pendiente múltiple que recorrería este bucle defensivo. Un intento de pagar la anterior devolvió 409; no se conservó esa prueba con una expectativa incorrecta ni se inventó una concurrencia real. |
| `realtime.py:297` | Marcado degradado tras heartbeat sin frescura. Se cubren fallos de conexión y estado del broker; este punto de la tarea periódica no se fuerza con esperas reales en los nuevos casos. |
| `realtime.py:356` | Cancelación de la tarea heartbeat en el finally del listener. Se cubren cancelación en lifespan y listener sin heartbeat; el recorrido con tarea periódica creada y fallo de conexión queda sin ejecutar aquí. Los destinos de ramas de este módulo sí quedan al 100 %, lo que ilustra que ramas y líneas no son equivalentes. |
| `release_payouts.py:48`, rama `47→48` | Guarda `if __name__ == "__main__"`. Se prueba `main()` como función pública con composición controlada; no se ejecuta un proceso CLI que pudiera heredar configuración local y acceder a una base real. Queda exceptuado el wrapper, no las salidas de negocio comprobadas. |

Las excepciones de S3 son **por línea** y no implican que los módulos completos alcancen 100 %. No se añadieron `pragma: no cover`, exclusiones nuevas o mocks del código que se pretendía medir para ocultarlas.

### Frontend

Quedan tres bloques no visitados en el ámbito puro: uno en `chat-events.ts:62` y dos en `provider-profile-api.ts:110,112`, según los contadores V8. Son variantes de guardas de payload y errores de campo. Se cubren otros valores inválidos y rutas de rechazo, pero no todas sus combinaciones de cortocircuito; los módulos quedan respectivamente en **97,96 % y 95,83 % de ramas**, por encima del objetivo. No se declara cobertura de condiciones completa.

`supabase/client.ts:4–26` permanece con **11,54 % de líneas y 0 % de funciones**. Su responsabilidad es configurar `createBrowserClient`, no lógica pura. Para mantener las pruebas sin navegador ni red se reemplazó ese límite en los nuevos casos. Su integración real, variables públicas y comportamiento del SDK requieren pruebas de navegador separadas; no se atribuye una verificación de seguridad del SDK a esta exclusión.

El loader preexistente `tests/support/alias-loader.mjs` conserva líneas 15 y 27–29 no cubiertas (86,67 % de líneas). Es infraestructura de pruebas y no forma parte de `src/lib`; el resultado bruto sigue mostrándolo.

## 9. Defectos encontrados

### D1. Fecha fija que convierte un caso válido en inválido

- **Ubicación:** `backend/tests/test_public_provider_routes.py:399`, con fallo observado en la aserción de estado de la línea 408.
- **Severidad:** media para confiabilidad de la suite; no es un defecto de producción.
- **Causa:** `requestedAt="2026-11-08T10:00:00-03:00"` pasó a estar en el pasado. El 2026-11-09 el validador productivo la rechazó correctamente.
- **Reproducción observada:** `uv run pytest tests/test_public_provider_routes.py::test_quote_request_uses_server_account_actor_and_creates_only_request -q`, resultado `assert 422 == 201`.
- **Corrección:** fixture de reloj que fija la validación al 2026-11-07 para ese módulo y el de viajes compartidos, preservando el significado histórico de las entradas. No se relajó la validación productiva ni se cambió la fecha al azar.
- **Auditoría adicional:** `test_chat_unread.py::test_marking_read_never_moves_the_last_read_time_backwards` comparaba contra un futuro fijo en 2030; se fijaron el reloj SQLite y la fecha de comparación. Era otro riesgo temporal latente, no un segundo fallo observado en la fecha de ejecución.
- **Verificación:** el caso y la suite completa pasan. Otros timestamps de historial, ordenamiento o fixtures con reloj explícito no se consideran errores solo por ser literales.
- **Límite de alcance:** se localizaron fechas futuras fijas en `frontend/tests/marketplace.spec.ts:361` y `frontend/tests/page-chat.spec.ts:73,75,534,542,556` (2099). Son pruebas E2E fuera de las superficies autorizadas; no se editaron. Deben migrarse a reloj de página fijo en una tarea específica.

### D2. Las opciones del motor pueden anular TLS obligatorio

- **Ubicación:** `backend/src/amira_api/db.py:34–35`.
- **Severidad:** media, con impacto potencial alto si un llamador interno configura explícitamente un modo inseguro; no se demostró entrada remota controlada por usuario.
- **Causa:** `options.update(engine_options)` reemplaza por completo el diccionario `connect_args` seguro definido antes. La URL mantiene `sslmode=require`, pero el argumento DBAPI enviado por el llamador contiene el override.
- **Reproducción sin conexión:** llamar `create_database_engine("postgresql://db/test", connect_args={"sslmode": "disable"})` con `create_engine` sustituido por un `Mock`; inspeccionar los kwargs recibidos. Se observó `sslmode="disable"`, no `"require"`.
- **Prueba retenida:** `test_whitebox_critical.py::test_database_tls_cannot_be_disabled_by_engine_options`, marcada `xfail(strict=True, reason="BUG: connect_args overrides mandatory TLS in create_database_engine")`.
- **Comando:** `uv run pytest tests/test_whitebox_critical.py::test_database_tls_cannot_be_disabled_by_engine_options -rx -q`.
- **Estado:** no corregido, por la prohibición de modificar producción. El `xfail` estricto producirá XPASS fallido cuando cambie el comportamiento y obliga a revisar la marca. No se abrió una conexión insegura para demostrar el defecto.
- **Recomendación:** en una tarea autorizada, combinar opciones de conexión y aplicar las garantías TLS después de cualquier override, conservando las opciones legítimas de pool y timeouts.

### D3. Pérdida de headers en la variante `Headers` de `RequestInit`

- **Ubicación:** `frontend/src/lib/auth/account-api.ts:42`.
- **Severidad:** media funcional. No se observó filtración de credenciales.
- **Causa:** expandir `...options.headers` copia propiedades de un registro simple, pero no las entradas de un objeto `Headers`, que es una variante válida de `RequestInit.headers`.
- **Reproducción:** llamar `authenticatedApiFetch` con `{ headers: new Headers({ Accept: "application/json" }) }` y un fetch stub; normalizar los headers recibidos con `new Headers(options.headers)`.
- **Esperado/observado:** `Accept="application/json"`; se obtuvo `null`. La autorización propia del wrapper se conserva.
- **Evidencia RED:** la prueba inicial sin TODO falló con `null !== 'application/json'`; los demás 26 casos del archivo pasaron.
- **Prueba retenida:** `whitebox-access.node-test.mjs`, `test.todo("BUG: authenticatedApiFetch drops Headers values from RequestInit", ...)`. El callback se ejecuta y sigue fallando de manera esperada.
- **Comando:** `node tests/unit/whitebox-access.node-test.mjs`, resumen final `26 pass / 0 fail / 1 todo` y diagnóstico de la aserción TODO.
- **Estado:** no corregido. A diferencia de `xfail(strict=True)`, un TODO de Node no impone automáticamente la misma disciplina ante un éxito inesperado; se debe revisar al corregir el wrapper.
- **Recomendación:** normalizar a `Headers` antes de aplicar la autorización, y comprobar también la variante de pares de headers en una tarea de corrección autorizada.

## 10. Riesgos, limitaciones y recomendaciones

### Lo que esta campaña no demuestra

1. **Concurrencia real:** se recorren errores de integridad y guardas bajo lock, pero SQLite y mocks no demuestran `FOR UPDATE`, `SKIP LOCKED` ni advisory locks entre procesos PostgreSQL.
2. **Integraciones reales:** transporte JWKS, Supabase, correo, almacenamiento y proveedor de pago fueron sustituidos. Se valida la reacción de la aplicación a respuestas controladas, no la disponibilidad ni los contratos de servicios alojados.
3. **Base PostgreSQL:** dos pruebas de `test_payment_db.py` y una de búsqueda pública se omitieron porque no estaba definido `AMIRA_TEST_DATABASE_URL`. No se configuró una base externa para evitar operaciones destructivas.
4. **Frontend completo:** `src/lib` no equivale a componentes, páginas, navegador o flujos E2E. Tampoco se midió todo archivo no importado del árbol: el runner nativo informa los módulos cargados por esta suite.
5. **Cobertura y oráculos:** ejecutar una línea no asegura que el resultado sea correcto. Los fallos esperados TLS y Headers alcanzan líneas cubiertas. Se mantienen verificaciones explícitas de estado, errores y efectos laterales para reducir este riesgo.
6. **Fechas fuera de alcance:** las fechas E2E señaladas siguen fijas. Se prefirió respetar las superficies autorizadas antes que cambiar silenciosamente otras pruebas.
7. **Avisos preexistentes:** pytest informa un aviso de deprecación del TestClient/httpx. La ejecución directa de archivos Node puede advertir sobre el tipo de módulo de `package.json`; no se cambió esa configuración, ajena al alcance.

### Recomendaciones de CI

Como siguiente paso, con autorización específica para modificar CI:

```bash
# Backend: punto inicial de protección de cobertura combinada.
uv run pytest --cov=amira_api --cov-branch --cov-report=term-missing --cov-fail-under=99
```

`--cov-fail-under=99` protege el porcentaje combinado, **no** un mínimo independiente de ramas por módulo. Para conservar S4/S5, conviene leer el JSON de coverage.py y verificar explícitamente el mínimo de ramas de cada módulo acordado. El umbral debe partir de estos resultados observados y permitir excepciones justificadas, no forzar exclusiones cosméticas.

En frontend, separar el presupuesto de `src/lib` del cableado del SDK y de los loaders. Se recomienda un umbral de al menos 95 % para líneas y ramas del ámbito puro, calculado sobre el resumen nativo, sin presentar la exclusión como cobertura total del navegador. No se añadió configuración de CI ni se modificó el runner solicitado.

Orden recomendado de seguimiento: corregir D2 y D3 en cambios de producción independientes con sus pruebas de regresión; eliminar las marcas esperadas solo tras observar la corrección; completar las pequeñas excepciones de configuración de S3; ejecutar las pruebas PostgreSQL contra una base local desechable autorizada; y estabilizar las fechas E2E dentro de su propio alcance.

## 11. Conclusión

La campaña añadió **215 casos de backend**, incluidos el fallo esperado estricto, y **36 casos de frontend**, incluido el TODO ejecutado. Mantuvo el código productivo intacto y elevó la cobertura con caminos de error y transacción observables, no con cambios para facilitar artificialmente la medición. Se alcanzaron los umbrales por módulo de S4, S5 y S6; las excepciones del objetivo crítico de S3 están identificadas y justificadas por línea.

El resultado entregable es este informe junto con las pruebas, la configuración reproducible de cobertura y los commits locales por tarea registrados en `odd/tasks/caja-blanca.md`. No se realizó push. Los dos defectos productivos y las integraciones omitidas requieren seguimiento separado; no quedan ocultos por el resultado de cobertura.
