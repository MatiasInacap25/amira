# 4.5 Plan de Pruebas

La realización de pruebas es fundamental en el ciclo de vida del software, debido a que es la fase en donde se verifica, mediante distintas técnicas, la efectividad y el correcto funcionamiento del software, comparándolo directamente con los requerimientos previamente estipulados en la fase de análisis.

Las pruebas descritas en este capítulo se ejecutaron el 9 de noviembre de 2026 sobre la versión del sistema integrada en la rama `develop` del repositorio. Los informes técnicos completos de cada prueba se encuentran en `docs/testing/` (`informe-caja-blanca.md`, `informe-caja-negra.md` e `informe-estres.md`).

## 4.5.1 Pruebas del Sistema

La solución Amira contempla dos artefactos de software: una **API de servicios (backend)**, desarrollada con FastAPI sobre PostgreSQL (Supabase), y una **aplicación web (frontend)**, desarrollada con Next.js. Teniendo en cuenta esto, se realizan pruebas a cada uno de los artefactos por separado y en conjunto. A continuación, se detallan las pruebas realizadas por cada artefacto:

**API de servicios (backend)**

- **Pruebas de caja blanca:** se evalúa la cobertura de sentencias y de ramas del código fuente, con foco en autenticación, pagos, desembolsos y transiciones de estado.
- **Pruebas de caja negra:** se prueban funcionalidades a través de su contrato HTTP, sin acceso al código: navegar el catálogo, autenticarse, crear solicitudes, cotizar, pagar, ejecutar el servicio, reclamar y conversar por chat.
- **Pruebas de estrés:** se pone a prueba la cantidad de usuarios simultáneos que soporta el servidor desplegado y sus tiempos de respuesta.

**Aplicación web (frontend)**

- **Pruebas de caja blanca:** se evalúa la cobertura de la lógica pura de `src/lib` (validaciones, paginación, caché, manejo de errores y eventos de chat).
- **Pruebas de caja negra:** se verifican los flujos de usuario en el navegador mediante pruebas de extremo a extremo (E2E).

Por último, las pruebas de caja negra del backend ejercitan el ciclo de negocio completo (solicitud → cotización → pago → servicio → reclamo → desembolso), lo que constituye una prueba de integración entre la API, la base de datos y la autenticación.

### 4.5.1.1 Pruebas de Caja Negra

Este tipo de prueba se realiza para verificar si efectivamente una funcionalidad del sistema está bien realizada y desarrollada. Se lleva a cabo sobre la interfaz del software, introduciendo datos de entrada para estudiar si las salidas corresponden con las salidas esperadas.

En esta solución, el **oráculo de prueba** (la fuente de los resultados esperados) se limitó a las especificaciones: `PROJECT_OVERVIEW.md`, las reglas de negocio documentadas en `backend/README.md`, las especificaciones de cada funcionalidad (`odd/tasks/*.md`) y el esquema OpenAPI publicado por la propia API. En ningún caso se usó el código fuente para decidir el resultado esperado.

#### Entorno de prueba

| Elemento | Configuración |
|---|---|
| Servidor | API real ejecutada con Uvicorn como proceso independiente, en `127.0.0.1` |
| Base de datos | PostgreSQL 17 desechable (contenedor `amira_blackbox_db`), con todas las migraciones aplicadas |
| Autenticación | Servidor JWKS local que firma tokens con el mismo formato de Supabase, para cinco actores: cliente, otro cliente, dueño de empresa, otro dueño y conductor |
| Herramientas | pytest 8.4.2 y HTTPX 0.28.1 (backend); Playwright 1.63.0 con Chromium (frontend) |
| Técnicas | Particiones de equivalencia, análisis de valores límite, tablas de decisión y pruebas de transición de estados |

#### API de servicios (backend)

Las pruebas de caja negra de la API consisten en demostrar el correcto funcionamiento de las funcionalidades principales del negocio. A continuación se detallan los casos de prueba más representativos.

| Identificador | **CP001** |
|---|---|
| Requerimiento Asociado | Catálogo público de servicios (`backend/README.md`, *Public browse API*) |
| Flujo Asociado | Navegar el catálogo sin iniciar sesión |
| Nombre | Paginación y filtros del catálogo público |
| Descripción | En el presente caso de prueba se verifica que el catálogo público respete los límites de paginación y de filtros, y que no exponga datos privados de los proveedores. |
| Prerrequisitos | La API se encuentra en ejecución y existen proveedores publicados en la base de datos. No se requiere sesión. |
| Datos de Prueba | `GET /api/services` con: `limit` = 0, 1, 50 y 51; `offset` = 0, 5000 y 5001; `q` de 120 y 121 caracteres; `regionCode` de 1, 2 y 3 dígitos y con letras; `communeCode` de 4, 5 y 6 dígitos. |
| Resultados Esperados | Los valores dentro del rango (`limit` 1 a 50, `offset` 0 a 5000, `q` de hasta 120 caracteres, región de 2 dígitos, comuna de 5) responden **200**. Los valores fuera del rango responden **422**. Ninguna respuesta incluye correo, RUT ni claves privadas. |
| Resultado Obtenido | **Exitoso.** 41 de 41 pruebas del módulo aprobadas. |
| Post Condiciones | Sin cambios en la base de datos (operación de solo lectura). |

*Tabla 4.1: Prueba de Caja Negra CP001*

| Identificador | **CP002** |
|---|---|
| Requerimiento Asociado | Autenticación con Supabase y verificación de JWT (`backend/README.md`; `CLAUDE.md`, *Auth is split across two systems*) |
| Flujo Asociado | Iniciar sesión y acceder a recursos protegidos |
| Nombre | Tabla de decisión de autenticación |
| Descripción | Este caso de prueba demuestra que la API solo acepta tokens válidos, emitidos por el proveedor de identidad esperado y con el nivel de seguridad requerido. |
| Prerrequisitos | Servidor JWKS local activo. El usuario de prueba existe en la base de datos. |
| Datos de Prueba | `GET /api/account/me` con: sin token; token malformado; token vencido; emisor incorrecto; audiencia incorrecta; nivel `aal1` (sin SMS) frente a `aal2`; usuario anónimo; token válido. |
| Resultados Esperados | Solo el token válido con nivel `aal2` accede (**200**). Todas las demás combinaciones son rechazadas con **401** o **403**, sin crear registros. La identidad y el rol se toman del token verificado, nunca del cuerpo de la solicitud. |
| Resultado Obtenido | **Exitoso.** 18 de 18 pruebas del módulo aprobadas. |
| Post Condiciones | No se crean usuarios ni desafíos de verificación ante tokens rechazados. |

*Tabla 4.2: Prueba de Caja Negra CP002*

| Identificador | **CP003** |
|---|---|
| Requerimiento Asociado | Esquema `ServiceRequestCreate` (OpenAPI) |
| Flujo Asociado | Cliente solicita un servicio de transporte |
| Nombre | Crear solicitud de servicio |
| Descripción | Este caso de prueba demuestra que solo un cliente autenticado puede crear una solicitud, y que una solicitud inválida no deja registros en la base de datos. |
| Prerrequisitos | El usuario cliente ha iniciado sesión y existe un proveedor publicado con un tipo de servicio activo. |
| Datos de Prueba | Válidos: origen "Santiago", destino "Valparaíso", comunas 13101 y 05101, peso estimado 250,50 kg. Inválidos: direcciones vacías o excesivas, código de comuna inexistente, UUID malformado, carga negativa y campos adicionales no definidos. |
| Resultados Esperados | La solicitud válida responde **201** y queda registrada. Las solicitudes inválidas responden **422** y no se escribe ninguna fila. Un proveedor o un conductor que intenta crear una solicitud es rechazado. |
| Resultado Obtenido | **Exitoso.** |
| Post Condiciones | Existe una nueva solicitud en estado pendiente, asociada al cliente. |

*Tabla 4.3: Prueba de Caja Negra CP003*

| Identificador | **CP004** |
|---|---|
| Requerimiento Asociado | Esquema `QuotationCreate` (OpenAPI) |
| Flujo Asociado | Proveedor envía una cotización por el chat |
| Nombre | Crear cotización con valores límite |
| Descripción | Este caso de prueba verifica los límites de monto, vigencia y descripción de una cotización, y que solo el proveedor participante del chat pueda cotizar. |
| Prerrequisitos | Existe una solicitud aceptada por el proveedor, con su chat creado. El usuario proveedor ha iniciado sesión. |
| Datos de Prueba | Monto en CLP: 0, 1 y negativo. Vigencia: 0, 1, 168 y 169 horas. Descripción: 0, 1, 1000 y 1001 caracteres. Actores: proveedor participante, otro proveedor y cliente. |
| Resultados Esperados | Se aceptan montos enteros positivos, vigencias de 1 a 168 horas y descripciones de 1 a 1000 caracteres. Los valores fuera del rango responden **422**. Un actor que no participa en el chat es rechazado. |
| Resultado Obtenido | **Exitoso.** 29 de 29 pruebas del módulo de solicitudes y cotizaciones aprobadas. |
| Post Condiciones | La cotización válida queda visible en el chat del cliente. |

*Tabla 4.4: Prueba de Caja Negra CP004*

| Identificador | **CP005** |
|---|---|
| Requerimiento Asociado | Pagos con proveedor simulado (`backend/README.md`, *Payments*) |
| Flujo Asociado | Cliente paga una cotización |
| Nombre | Pago aprobado crea exactamente un servicio |
| Descripción | Este caso de prueba demuestra que un pago aprobado confirma un único servicio, que solo el cliente dueño puede usar el enlace de pago y que el webhook no puede aprobar pagos simulados. |
| Prerrequisitos | Existe una cotización vigente aceptada por el cliente y se ha generado su enlace de pago. |
| Datos de Prueba | Enlace firmado válido; enlace manipulado; enlace usado por otro cliente; webhook sin secreto, con secreto incorrecto y con secreto correcto. |
| Resultados Esperados | El pago aprobado crea **un** servicio confirmado. Un segundo intento de pago es rechazado. Un enlace manipulado o usado por otro cliente no se consume. El webhook sin secreto responde **401**, y con el proveedor simulado responde **403**. |
| Resultado Obtenido | **Exitoso.** 7 pruebas aprobadas (ver CP006 para el caso restante del módulo). |
| Post Condiciones | El servicio queda en estado confirmado, con su pago aprobado. |

*Tabla 4.5: Prueba de Caja Negra CP005*

| Identificador | **CP006** |
|---|---|
| Requerimiento Asociado | Pagos con proveedor simulado: *"the checkout link is single-use"* (`backend/README.md`) |
| Flujo Asociado | Cliente reutiliza un enlace de pago ya consumido |
| Nombre | Reutilizar enlace de pago consumido |
| Descripción | Este caso de prueba verifica que un enlace de pago, una vez usado, no pueda volver a usarse. |
| Prerrequisitos | Existe un pago ya aprobado mediante su enlace (CP005). |
| Datos de Prueba | Se vuelve a enviar el mismo token del enlace consumido, con `approve: true`. |
| Resultados Esperados | La solicitud es rechazada con un error de cliente (4xx). |
| Resultado Obtenido | **Fallido (defecto D1).** La API respondió **200 approved**. No se creó un segundo servicio ni hubo un segundo cobro, porque las confirmaciones son idempotentes. Severidad baja: hay una contradicción entre la especificación y el comportamiento. |
| Post Condiciones | Sigue existiendo un único servicio. El caso queda registrado como fallo esperado (`xfail` estricto) hasta que se corrija. |

*Tabla 4.6: Prueba de Caja Negra CP006*

| Identificador | **CP007** |
|---|---|
| Requerimiento Asociado | Ubicación en vivo del servicio (`backend/README.md`, *Live service location*) |
| Flujo Asociado | Conductor inicia el servicio y comparte su ubicación |
| Nombre | Iniciar servicio con ubicación del conductor |
| Descripción | Este caso de prueba demuestra que el servicio solo se inicia con una ubicación válida, que solo el conductor asignado puede actualizarla y que el cliente puede verla. |
| Prerrequisitos | Existe un servicio confirmado con conductor y vehículo asignados. El usuario conductor ha iniciado sesión. |
| Datos de Prueba | Latitud y longitud dentro de los límites, en los extremos (±90 y ±180) y fuera de ellos; inicio sin posición; actualización por el conductor asignado, el dueño no asignado y un tercero. |
| Resultados Esperados | Con una posición válida, el servicio pasa a "en curso". Con una posición inválida o ausente responde **422** y el servicio sigue confirmado. Solo el conductor asignado actualiza la posición. Completar el servicio antes de iniciarlo es rechazado. |
| Resultado Obtenido | **Exitoso.** 25 de 25 pruebas del módulo de ciclo de vida aprobadas. |
| Post Condiciones | Al completar el servicio con la foto de entrega (máximo 8 MiB), la posición en vivo se elimina. |

*Tabla 4.7: Prueba de Caja Negra CP007*

| Identificador | **CP008** |
|---|---|
| Requerimiento Asociado | Reclamos, conformidad y liberación de pagos (`backend/README.md`, *Claims, consent and payout release*) |
| Flujo Asociado | Cliente da conformidad o reclama un servicio completado |
| Nombre | Reclamo, conformidad y elegibilidad de desembolso |
| Descripción | Este caso de prueba verifica las reglas de reclamo y conformidad, y que el desembolso al proveedor solo se libere cuando corresponda. |
| Prerrequisitos | Existe un servicio completado y pagado. El usuario cliente dueño del servicio ha iniciado sesión. |
| Datos de Prueba | Motivo de reclamo vacío, solo espacios, de 1, 1000 y 1001 caracteres; reclamo fuera de la ventana de 24 horas; reclamo de un cliente ajeno; conformidad después de un reclamo. |
| Resultados Esperados | Se aceptan motivos de 1 a 1000 caracteres, y el reclamo pasa el servicio a "en disputa". Un reclamo abierto bloquea la conformidad. Fuera de la ventana de 24 horas o con un cliente ajeno, se rechaza. El desembolso solo se libera con conformidad (o vencimiento), un pago aprobado y una cuenta habilitada, descontando una comisión del 10 %, y no se duplica. |
| Resultado Obtenido | **Exitoso.** 16 de 16 pruebas del módulo aprobadas. |
| Post Condiciones | El desembolso queda registrado una sola vez, por el monto neto. |

*Tabla 4.8: Prueba de Caja Negra CP008*

| Identificador | **CP009** |
|---|---|
| Requerimiento Asociado | Chat y adjuntos (`backend/README.md`, *Chat real-time events* y *Chat attachments*) |
| Flujo Asociado | Cliente y proveedor conversan por chat |
| Nombre | Enviar mensajes y adjuntos en el chat |
| Descripción | Este caso de prueba verifica los límites de mensajes y adjuntos, y que solo los participantes accedan al chat. |
| Prerrequisitos | Existe un chat entre un cliente y un proveedor. Ambos han iniciado sesión. |
| Datos de Prueba | Mensajes de 0, 1, 2000 y 2001 caracteres; adjunto no imagen, de 5 MiB y de 5 MiB + 1 byte; acceso de un usuario no participante; token enviado en la URL del canal de eventos. |
| Resultados Esperados | Se aceptan mensajes de 1 a 2000 caracteres y adjuntos de imagen de hasta 5 MiB (el tipo se detecta por el contenido, no por la extensión). Un no participante es rechazado. El canal de eventos exige el token en la cabecera `Authorization` y lo rechaza en la URL. Marcar como leído responde **204**. |
| Resultado Obtenido | **Exitoso.** 13 de 13 pruebas del módulo aprobadas. |
| Post Condiciones | El contador de no leídos de la contraparte aumenta con cada mensaje nuevo. |

*Tabla 4.9: Prueba de Caja Negra CP009*

| Identificador | **CP010** |
|---|---|
| Requerimiento Asociado | Panel de proveedores y vehículos (`odd/tasks/panel-proveedores.md` S3; `backend/README.md`, *Provider vehicles*) |
| Flujo Asociado | Proveedor administra su perfil público y sus vehículos |
| Nombre | Publicar perfil y registrar vehículos |
| Descripción | Este caso de prueba demuestra que un perfil solo se publica cuando está completo, y valida los datos de los vehículos. |
| Prerrequisitos | El usuario dueño de empresa ha iniciado sesión. |
| Datos de Prueba | Perfil incompleto y completo; año del vehículo 1885, 1886, 2200 y 2201; peso 0 y 1; patente duplicada después de normalizarla; eliminación de un vehículo asignado a un servicio; acceso de un cliente o un conductor. |
| Resultados Esperados | Un perfil incompleto no se publica, y si se guarda incompleto se despublica solo. Se aceptan años de 1886 a 2200 y pesos mayores que cero. Una patente duplicada se rechaza. Un vehículo asignado no se puede eliminar (**409**). Solo el dueño accede a estas rutas. |
| Resultado Obtenido | **Exitoso.** 25 de 25 pruebas del módulo aprobadas. |
| Post Condiciones | El perfil publicado aparece en el catálogo público (CP001). |

*Tabla 4.10: Prueba de Caja Negra CP010*

**Resumen de resultados de la API**

| Módulo de prueba | Aprobadas | Fallidas | Fallo esperado |
|---|---:|---:|---:|
| Catálogo público | 41 | 0 | 0 |
| Autenticación y cuentas | 18 | 0 | 0 |
| Solicitudes y cotizaciones | 29 | 0 | 0 |
| Pagos | 7 | 0 | 1 |
| Ciclo de vida del servicio | 25 | 0 | 0 |
| Reclamos y desembolsos | 16 | 0 | 0 |
| Chat | 13 | 0 | 0 |
| Perfil de proveedor, vehículos e imágenes | 25 | 0 | 0 |
| Invitaciones y viajes compartidos | 19 | 0 | 0 |
| Arnés de prueba | 2 | 0 | 0 |
| **Total** | **195** | **0** | **1** |

*Tabla 4.11: Resumen de Pruebas de Caja Negra de la API*

#### Aplicación web (frontend)

Las pruebas de caja negra de la aplicación web se realizan con Playwright, que controla un navegador Chromium y recorre las pantallas como lo haría un usuario: registro, inicio de sesión, catálogo, solicitudes, chat, pagos, panel del proveedor, vehículos, invitaciones y viajes compartidos. La aplicación se levanta en una copia aislada (`127.0.0.1:3179`), con un servicio de autenticación simulado.

| Medida | Resultado |
|---|---|
| Archivos de prueba | 31 |
| Pruebas aprobadas | **427** |
| Pruebas fallidas | 0 |
| Pruebas inestables (*flaky*) | 0 |

*Tabla 4.12: Resultado de Pruebas E2E de la Aplicación Web*

### 4.5.1.2 Pruebas de Caja Blanca

Las pruebas de caja blanca se realizan accediendo al código fuente de los artefactos que componen la solución, centrándose en sus detalles procedimentales. Se mide qué sentencias y qué ramas de decisión (cada `if`, cada camino de error) son ejecutadas por las pruebas, y se escriben pruebas nuevas para los caminos que no se estaban recorriendo.

#### API de servicios (backend)

El software utilizado para medir la cobertura del código de la API es **coverage.py**, mediante el complemento **pytest-cov**, con medición de ramas activada (`branch = true`).

**Cobertura de código**

Antes de la campaña se midió una línea base. Luego se agregaron pruebas para los caminos sin cubrir, con prioridad en los módulos críticos: autenticación, pagos, desembolsos y conexión a la base de datos. Los resultados se ilustran a continuación:

- Sentencias totales: 4.047
- Sentencias sin ejecutar: de 243 a **9**
- Ramas de decisión: 804; ramas parciales, de 98 a **8**

```text
$ uv run pytest --cov=amira_api --cov-branch
Name        Stmts   Miss Branch BrPart  Cover
---------------------------------------------
TOTAL        4047      9    804      8    99%
1071 passed, 3 skipped, 1 xfailed
```

*Figura 4.1: Cobertura de Código de la API*

| Medida | Inicial | Final |
|---|---:|---:|
| Cobertura de sentencias | 94,00 % | **99,78 %** |
| Cobertura de ramas | 84,58 % | **99,00 %** |
| Cobertura combinada | 92,43 % | **99,65 %** |
| Pruebas aprobadas / fallidas | 856 / 1 | **1071 / 0** |

*Tabla 4.13: Evaluación General de Cobertura de la API*

**Evaluación por módulo**

Los módulos más críticos del negocio alcanzaron cobertura total o casi total:

| Módulo | Responsabilidad | Inicial | Final |
|---|---|---:|---:|
| `auth.py` | Verificación de JWT contra JWKS | 88,06 % | **100 %** |
| `db.py` | Conexión TLS y límites del pool | 61,90 % | **100 %** |
| `account_routes.py` | Creación de cuentas | 65,26 % | **98,42 %** |
| `invitation_routes.py` | Invitaciones de conductores | 74,34 % | **98,23 %** |
| `payment_service.py` | Transacción de pago | 89,76 % | **98,43 %** |
| `payout_service.py` | Liberación de desembolsos | 95,65 % | **100 %** |
| `fallback_routes.py` | Verificación alternativa por correo | 86,54 % | **100 %** |
| `vehicle_routes.py` | Vehículos del proveedor | 84,67 % | **100 %** |

*Tabla 4.14: Cobertura de Módulos Críticos de la API*

Las 9 sentencias que quedaron sin cubrir están justificadas una por una en el informe técnico. Se trata de guardas defensivas inalcanzables con datos válidos y de configuraciones incompletas de entorno. No se agregaron exclusiones (`pragma: no cover`) para elevar artificialmente el resultado.

#### Aplicación web (frontend)

El software utilizado para medir la cobertura de la lógica de la aplicación web es el ejecutor de pruebas nativo de **Node.js** (`node --test --experimental-test-coverage`), que usa el motor de cobertura de V8.

| Medida | Inicial | Final |
|---|---:|---:|
| Cobertura de líneas | 88,91 % | **97,77 %** |
| Cobertura de ramas | 96,15 % | **98,96 %** |
| Cobertura de funciones | 83,78 % | **99,12 %** |
| Líneas de lógica pura (`src/lib`) | 90,73 % | **100 %** |

*Tabla 4.15: Evaluación General de Cobertura de la Aplicación Web*

Los módulos con mayor mejora fueron `auth/account-api.ts` (de 20 % a 100 % de líneas), `provider-request-access.ts` (de 57,14 % a 100 %) y `provider-profile-api.ts` (de 80,39 % a 100 %).

#### Defectos encontrados

Uno de los beneficios de las pruebas de caja blanca es que revelan defectos que las pruebas funcionales no ven:

| Id. | Defecto | Severidad | Estado |
|---|---|---|---|
| D1 | Una prueba existente usaba una fecha fija (8 de noviembre de 2026) y empezó a fallar sola cuando esa fecha pasó. | Media | **Corregido**: ahora usa un reloj controlado. |
| D2 | `db.py`: pasar `connect_args` a la creación del motor reemplaza la configuración que exige TLS. | Baja (latente: ningún llamador lo hace hoy) | Registrado como fallo esperado. |
| D3 | `account-api.ts`: las cabeceras se pierden cuando se entregan como objeto `Headers`. | Baja (latente: ningún llamador lo hace hoy) | Registrado como prueba pendiente. |

*Tabla 4.16: Defectos Encontrados en Pruebas de Caja Blanca*

### 4.5.1.3 Pruebas de Estrés del Software

Este tipo de pruebas se realiza para determinar el rendimiento del sistema bajo cierto nivel de presión de trabajo, ya sea con técnicas como consultas o conexiones simultáneas, pruebas de carga, etc.

#### API de servicios (backend)

La plataforma utilizada para probar el rendimiento de la API es **k6** (versión 2.3.0, de Grafana Labs). k6 es una herramienta de línea de comandos en la que se define, mediante un script, la cantidad de usuarios virtuales, los endpoints a consultar y los umbrales de aceptación. El script de la prueba se encuentra en `k6/scripts/stress-public-read.js`.

**Entorno bajo prueba**

| Componente | Configuración |
|---|---|
| Servidor | Render, plan gratuito: 1 instancia, 0,15 vCPU y 512 MB de RAM, región Oregon |
| Aplicación | Uvicorn con 1 proceso de trabajo |
| Base de datos | Supabase (PostgreSQL 17), pool de 10 conexiones |
| Origen de la carga | Estación local en Chile |

*Tabla 4.17: Entorno de la Prueba de Estrés*

**Diseño de la prueba**

Se simularon usuarios que consultan el catálogo público con una pausa de 3 a 5 segundos entre acciones, igual que un usuario real. La carga se aumentó de forma escalonada: 1 → 10 → 25 → 50 → 100 → 200 → 300 usuarios simultáneos. Las solicitudes se repartieron así: 30 % `/health`, 30 % listado de servicios, 15 % tipos de servicio, 15 % detalle de proveedor y 10 % catálogo de comunas. Solo se usaron operaciones de lectura, para no alterar los datos.

Como criterios de aceptación se definieron dos umbrales que detienen la prueba automáticamente si se superan:

- Tasa de errores menor al 5 %.
- Tiempo de respuesta del percentil 95 (p95) menor a 3 segundos.

**Resultados**

Como resumen del procedimiento, k6 registró 3.972 solicitudes, con 97,80 % de respuestas correctas, y detuvo la prueba a los 7 minutos y 48 segundos, en el escalón de 200 usuarios, al superar el umbral de tiempo de respuesta (p95 = 3,44 s).

```text
checks.........................: 97.80% ✓ 3885     ✗ 87
http_req_duration..............: avg=1.34s  med=251.79ms  p(95)=3.44s  p(99)=25.23s
http_req_failed................: 2.19%  ✓ 87       ✗ 3885
http_reqs......................: 3972   8.49/s
vus............................: 200    min=1  max=200
thresholds on metrics 'http_req_duration' were crossed; stopping test prematurely
```

*Figura 4.2: Reporte Resumen de la Prueba de Estrés*

El comportamiento por escalón de carga se detalla en la siguiente tabla:

| Usuarios simultáneos | Solicitudes por segundo | Errores | Tiempo de respuesta (p95) | Estado |
|---:|---:|---:|---:|---|
| 1 | 0,2 | 0 % | 213 ms | Estable |
| 10 | 2,4 | 0 % | 242 ms | Estable |
| 25 | 6,0 | 0 % | 234 ms | Estable |
| 50 | 12,0 | 0 % | 267 ms | Estable |
| 100 | 21,1 | 0 % | 2.112 ms | Saturado |
| 200 | 4,0 | 54,5 % | 28.975 ms | Colapso |

*Tabla 4.18: Rendimiento por Escalón de Carga*

Se debe tener en cuenta el criterio de aceptación de que el tiempo de respuesta no debe superar los 3 segundos. Hasta **50 usuarios simultáneos**, la prueba es exitosa: el tiempo de respuesta se mantiene en unos 260 ms, que corresponden casi por completo a la latencia de red entre Chile y el servidor. Con **100 usuarios**, el sistema sigue sin errores, pero alcanza su capacidad máxima de unas **21 solicitudes por segundo** y el tiempo de respuesta sube a unos 2 segundos. Con **200 usuarios**, el rendimiento cae a 4 solicitudes por segundo y fallan más de la mitad de las solicitudes.

**Uso de recursos del servidor**

Las métricas de Render durante la prueba permiten identificar el recurso limitante:

| Minuto (UTC) | CPU | % del límite | Memoria |
|---|---:|---:|---:|
| 20:22 | 0,012 vCPU | 8 % | 98 MB |
| 20:24 | 0,050 vCPU | 33 % | 99 MB |
| 20:26 | 0,116 vCPU | 78 % | 108 MB |
| 20:27 | **0,136 vCPU** | **91 %** | 120 MB (23 %) |

*Tabla 4.19: Uso de Recursos del Servidor Durante la Prueba*

El recurso que se agota es la **CPU**: llegó al 91 % del límite del plan, mientras la memoria se mantuvo en un 23 %. Al terminar la prueba el servicio se recuperó solo y volvió a responder en unos 0,2 segundos. El consumo de cuota fue de 7,8 MB transferidos, menos del 0,01 % del plan gratuito.

**Conclusión de la prueba de estrés**

Teniendo en cuenta lo anterior, el resultado de la prueba es **positivo para el uso actual** de la demostración, ya que la capacidad medida (unos 100 usuarios activos) supera ampliamente la demanda real. También quedó establecido el límite del sistema: para atender más de 100 usuarios simultáneos se recomienda pasar a un plan con al menos 0,5 vCPU, ejecutar Uvicorn con 2 procesos de trabajo y limitar la concurrencia, para que ante una sobrecarga el servicio rechace rápido en lugar de colapsar.

## 4.5.2 Resumen de Resultados

| Prueba | Artefacto | Herramienta | Resultado | Defectos |
|---|---|---|---|---|
| Caja negra | API | pytest + HTTPX sobre una API real | 195 aprobadas, 1 fallo esperado | 1: el enlace de pago se puede reutilizar (severidad baja) |
| Caja negra | Aplicación web | Playwright | 427 aprobadas en 31 archivos | Ninguno |
| Caja blanca | API | coverage.py / pytest-cov | 99,78 % de sentencias y 99,00 % de ramas | 2: fecha fija (corregido) y TLS reemplazable (latente) |
| Caja blanca | Aplicación web | Node.js / V8 | 97,77 % de líneas y 98,96 % de ramas | 1: cabeceras `Headers` (latente) |
| Estrés | API desplegada | k6 | Estable hasta 50 usuarios; capacidad máxima ~21 solicitudes/s (~100 usuarios) | Límite de CPU del plan gratuito |

*Tabla 4.20: Resumen del Plan de Pruebas*

En conclusión, el sistema cumple con las funcionalidades especificadas. Las pruebas encontraron cuatro defectos: el de mayor impacto (la prueba con fecha fija) ya fue corregido, y los demás son de severidad baja y quedaron registrados para corregirse. Además, las pruebas de estrés establecieron con datos medidos la capacidad del entorno de demostración y las mejoras necesarias para escalarlo.
