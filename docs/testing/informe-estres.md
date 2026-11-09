# Informe de prueba de estrés

**Fecha de ejecución:** 2026-11-09, 20:19:06 a 20:26:55 UTC (17:19 a 17:26 hora de Chile).
**Objetivo de la prueba:** backend de demostración `https://amira-1hfu.onrender.com` (Render, servicio `amira`).
**Herramienta:** k6 v2.3.0, ejecutado desde una estación local en Chile.
**Script:** `k6/scripts/stress-public-read.js`.

## Resumen ejecutivo

El backend de demostración atiende sin degradación hasta **50 usuarios concurrentes (~12 solicitudes por segundo)**, con un p95 de unos 260 ms. Con **100 usuarios (~21 solicitudes por segundo)** sigue sin errores, pero el p95 sube a unos 2 s. Al subir a **200 usuarios**, el servicio colapsa: el rendimiento cae de 21 a 4 solicitudes por segundo, aparecen *timeouts* de 30 s y la tasa de errores llega al 54,5 %. k6 abortó la prueba automáticamente a los 7 min 48 s, al superar el umbral de p95 de 3 s.

**El punto de quiebre está entre 100 y 200 usuarios concurrentes, con un techo de capacidad de ~21 solicitudes por segundo.** El recurso que se agota es la **CPU** de la instancia (0,136 de 0,15 vCPU, un 91 %). La memoria no fue un límite (23 %). El servicio se recuperó solo al terminar la carga, sin intervención.

El consumo de cuota fue mínimo: 7,8 MB recibidos (~0,008 % del ancho de banda mensual de Render).

## 1. Alcance y restricciones acordadas

- **Solo endpoints de lectura** y públicos, sin autenticación. No se ejecutaron escrituras, para no alterar los datos de la demo.
- Carga máxima de **300 usuarios virtuales**, definida con el usuario para no agotar el plan gratuito.
- **Corte automático** si la tasa de errores supera el 5 % o el p95 supera 3 s (`abortOnFail`, con 30 s de gracia para evaluar).
- La prueba se ejecutó con la demo sin otros usuarios activos.

## 2. Entorno bajo prueba

| Componente | Configuración |
|---|---|
| Render | Plan `free`, 1 instancia, región Oregon, Docker |
| CPU / memoria (medidos en Render) | Límite de 0,15 vCPU / 512 MB |
| Servidor de aplicación | `uvicorn` con 1 worker (`backend/Dockerfile`) |
| Pool de base de datos | `pool_size=5`, `max_overflow=5` (10 conexiones), `pool_timeout=10`, `statement_timeout=5000` (`backend/src/amira_api/db.py`) |
| Base de datos | Supabase, proyecto `Amira`, us-west-2, PostgreSQL 17 |
| Generador de carga | k6 v2.3.0 desde Chile (la latencia de red a Oregon aporta ~180 a 200 ms de base) |

## 3. Diseño de la prueba

**Modelo:** cerrado (`ramping-vus`), con un tiempo de pensamiento aleatorio de 3 a 5 s por iteración, para simular usuarios reales.

**Escalones** (rampa de 30 s y meseta de 1 min en cada uno):

| Fase | Usuarios virtuales |
|---|---|
| Calentamiento | 1 (1 min) |
| Escalón 1 | 10 |
| Escalón 2 | 25 |
| Escalón 3 | 50 |
| Escalón 4 | 100 |
| Escalón 5 | 200 |
| Escalón 6 | 300 (no se alcanzó, por el aborto) |

**Mezcla de endpoints** (ponderada por iteración):

| Endpoint | Peso | Toca la base de datos |
|---|---|---|
| `GET /health` | 30 % | No |
| `GET /api/services` | 30 % | Sí |
| `GET /api/service-types` | 15 % | Sí |
| `GET /api/providers/{id}` | 15 % | Sí |
| `GET /api/locations` | 10 % | Sí (respuesta de ~13 KB) |

**Umbrales:** `http_req_failed rate<0.05` y `http_req_duration p(95)<3000`, ambos con aborto. Además se definieron umbrales p95 por endpoint para obtener métricas separadas por endpoint.

**Validación previa:** `k6 inspect` (estructura válida) y una prueba de humo de 3 iteraciones (3/3 con respuesta 200).

## 4. Resultados globales

| Métrica | Valor |
|---|---|
| Duración efectiva | 7 min 48 s (abortada) |
| Solicitudes totales | 3.972 (8,49 por segundo de promedio) |
| Verificaciones `status 200` | 97,80 % (3.885 correctas, 87 fallidas) |
| `http_req_failed` | 2,19 % (umbral global < 5 %: cumplido) |
| `http_req_duration` p50 / p90 / p95 / p99 / máx. | 252 ms / 1,79 s / **3,44 s** / 25,23 s / 30 s |
| Datos recibidos / enviados | 7,8 MB / 550 kB |
| Máximo de usuarios alcanzado | 200 |
| Código de salida de k6 | 99 (umbral superado; aborto esperado) |

**Umbral que provocó el aborto:** p95 global de 3,44 s, mayor que el límite de 3 s. También superaron el límite los endpoints `provider`, `service-types` y `services`.

### Por endpoint

| Endpoint | prom. | p50 | p95 | p99 | máx. | Umbral p95 < 3 s |
|---|---|---|---|---|---|---|
| `health` | 1,05 s | 212 ms | 2,17 s | 17,37 s | 22,43 s | ✓ |
| `locations` | 1,23 s | 258 ms | 2,79 s | 25,65 s | 30 s | ✓ |
| `service-types` | 1,35 s | 233 ms | 3,13 s | 19,57 s | 30 s | ✗ |
| `services` | 1,54 s | 286 ms | **7,36 s** | 25,66 s | 29,98 s | ✗ |
| `provider` | 1,64 s | 302 ms | 3,58 s | 26,58 s | 30 s | ✗ |

Incluso `/health`, que no consulta la base, se degradó hasta 22 s. Esto confirma que el cuello de botella es el proceso de la aplicación (CPU y un solo worker), y no solo la base de datos.

## 5. Comportamiento por escalón (ventanas de 30 s)

| t (s) | Usuarios | Solicitudes/s | Errores | p50 | p95 | máx. |
|---|---|---|---|---|---|---|
| 0 | 1 | 0,2 | 0 % | 214 ms | 611 ms | 611 ms |
| 30 | 1 | 0,2 | 0 % | 202 ms | 213 ms | 213 ms |
| 60 | 9 | 1,3 | 0 % | 215 ms | 351 ms | 632 ms |
| 90 | 10 | 2,4 | 0 % | 204 ms | 235 ms | 604 ms |
| 120 | 10 | 2,4 | 0 % | 202 ms | 242 ms | 292 ms |
| 150 | 24 | 4,3 | 0 % | 203 ms | 233 ms | 795 ms |
| 180 | 25 | 5,9 | 0 % | 203 ms | 330 ms | 616 ms |
| 210 | 25 | 6,0 | 0 % | 201 ms | 234 ms | 281 ms |
| 240 | 49 | 9,0 | 0 % | 202 ms | 267 ms | 358 ms |
| 270 | 50 | 11,9 | 0 % | 201 ms | 262 ms | 644 ms |
| 300 | 50 | 12,0 | 0 % | 203 ms | 267 ms | 505 ms |
| 330 | 99 | 16,7 | 0 % | 268 ms | 2.073 ms | 3.675 ms |
| 360 | 100 | 20,6 | 0 % | 581 ms | 2.010 ms | 3.104 ms |
| 390 | 100 | 21,1 | 0 % | 657 ms | 2.112 ms | 4.065 ms |
| 420 | 199 | 14,3 | 4,9 % | 1.080 ms | 11.457 ms | 14.475 ms |
| 450 | 200 | **4,0** | **54,5 %** | 19.523 ms | 28.975 ms | 30.001 ms |

**Lectura de la tabla:**
1. **Zona estable (1 a 50 usuarios):** la latencia se mantiene plana en ~200 ms, que es básicamente el viaje de red Chile ↔ Oregon. El rendimiento crece en proporción a la carga.
2. **Zona de saturación (100 usuarios):** el rendimiento se estanca en ~21 solicitudes por segundo y la latencia se multiplica por 8 a 10 (p95 ~2 s), porque las solicitudes empiezan a hacer cola. Todavía no hay errores.
3. **Zona de colapso (200 usuarios):** el rendimiento **cae** de 21 a 4 solicitudes por segundo (colapso por congestión). Las solicitudes alcanzan el *timeout* de 30 s del cliente y la tasa de errores llega al 54,5 %.

## 6. Recursos del servidor (métricas de Render)

| Minuto (UTC) | CPU (máx.) | % del límite de 0,15 | Memoria |
|---|---|---|---|
| 20:20 | 0,004 | 3 % | 98 MB |
| 20:22 | 0,012 | 8 % | 98 MB |
| 20:24 | 0,050 | 33 % | 99 MB |
| 20:25 | 0,071 | 48 % | 99 MB |
| 20:26 | 0,116 | 78 % | 108 MB |
| 20:27 | **0,136** | **91 %** | 120 MB (23 % de 512 MB) |
| 20:28 | 0 | 0 % | 120 MB |

La CPU llegó al 91 % del límite en el minuto del colapso. La memoria se mantuvo holgada. La métrica de solicitudes HTTP de Render no está disponible en el plan gratuito, y la de ancho de banda todavía no reflejaba la ventana de la prueba al momento de la consulta.

**Recuperación:** después de la prueba, tres solicitudes a `/api/services` respondieron 200 en 0,21 a 0,24 s. El servicio no se reinició ni quedó degradado.

## 7. Hallazgos

| # | Hallazgo | Evidencia | Impacto |
|---|---|---|---|
| E1 | **Arranque en frío de ~24 s** | El primer `GET /health` antes de la prueba tardó 23,8 s | El primer usuario después de 15 min de inactividad espera ~24 s. Propio del plan gratuito |
| E2 | **Capacidad máxima de ~21 solicitudes/s** | Meseta a 100 usuarios | Con un tiempo de pensamiento de 3 a 5 s, equivale a ~100 usuarios activos simultáneos |
| E3 | **Colapso por congestión por encima de la capacidad** | De 21 a 4 solicitudes/s con 200 usuarios | Superar el límite no degrada de forma gradual: el rendimiento se desploma y fallan más de la mitad de las solicitudes |
| E4 | **CPU como recurso limitante** | 0,136 de 0,15 vCPU | El plan gratuito tiene una fracción de vCPU; 1 worker de uvicorn no puede paralelizar trabajo de CPU |
| E5 | **No hay *backpressure*** | *Timeouts* de 30 s en lugar de rechazos rápidos (503) | Los clientes esperan hasta el *timeout*; no hay límite de concurrencia ni de cola en la aplicación |

## 8. Consumo de cuota

| Recurso | Consumo de la prueba | Límite mensual (plan gratuito) | % |
|---|---|---|---|
| Ancho de banda de Render (salida) | ~7,8 MB | ~100 GB | ~0,008 % |
| Horas de instancia de Render | ~0,15 h | 750 h | ~0,02 % |
| *Egress* de Supabase (estimado: 70 % de las respuestas consultan la base) | ≤ ~6 MB | 5 GB | ≤ ~0,12 % |

La estimación previa del peor caso era de 0,5 GB. El consumo real fue unas 60 veces menor, porque el servicio se saturó antes de servir el volumen teórico y el corte automático detuvo la prueba.

## 9. Recomendaciones

Ordenadas por costo y beneficio:

1. **Demo sin cambios:** es suficiente para el uso actual (1 o 2 personas). La capacidad medida (~100 usuarios activos) supera con creces la demanda real.
2. **Antes de abrir la demo a más usuarios:**
   - Subir a un plan con al menos 0,5 vCPU (por ejemplo, Starter) y ejecutar `uvicorn` con 2 workers. Es el único cambio que ataca el cuello de botella medido (E4).
   - Volver a medir con este mismo script para cuantificar la mejora.
3. **Limitar la concurrencia** (por ejemplo, `--limit-concurrency` de uvicorn, o *rate limiting*) para que, ante una sobrecarga, el servicio responda 503 rápido en lugar de colapsar (E3 y E5).
4. **Caché de respuestas públicas casi estáticas:** `/api/locations` (13 KB) y `/api/service-types` cambian rara vez. Un `Cache-Control` o una caché en memoria reduce CPU y *egress*.
5. **Evitar el arranque en frío** (E1): un plan pagado no duerme. Con el plan gratuito, se puede aceptar como una limitación conocida de la demo.
6. **Pool de base de datos:** no fue el límite observado en esta prueba, porque la CPU se saturó primero. Si se suben la CPU y los workers, hay que revisar `pool_size` y `max_overflow` (10 conexiones por worker) frente al límite de conexiones de Supabase.

## 10. Limitaciones de esta prueba

- Solo se ejercitaron lecturas públicas. No se midieron flujos autenticados (validación de JWT contra JWKS), escrituras, pagos ni el *stream* en tiempo real.
- Generador único desde Chile: la latencia base (~200 ms) incluye la red.
- La prueba se abortó en el escalón de 200 usuarios, así que no se observó el escalón de 300 (era innecesario: el colapso ya era evidente).
- Las métricas de Render tienen una granularidad de 1 minuto.
- La base de datos de la demo tiene pocos datos. Con un volumen real, las consultas de `/api/services` serían más costosas.

## 11. Reproducción

```bash
# Requisito: k6 >= 2.3 (por ejemplo, `mise use -g k6@latest`)
SUMMARY_JSON=k6-summary.json k6 run --out csv=stress.csv k6/scripts/stress-public-read.js

# Contra otro entorno:
BASE_URL=https://<staging> PROFILE_ID=<uuid> k6 run k6/scripts/stress-public-read.js
```

Para ver el desglose por escalón, se agrupan las métricas `http_req_duration`, `http_req_failed` y `vus` del CSV en ventanas de 30 s.

## 12. Conclusión

El backend de demostración en el plan gratuito de Render soporta con holgura el uso actual. Su capacidad práctica es de **~21 solicitudes por segundo (~100 usuarios activos)** con latencia aceptable. Más allá de eso, colapsa por saturación de CPU en lugar de degradarse de forma gradual. La prueba se ejecutó de forma controlada, se detuvo sola al cruzar el umbral acordado, consumió una fracción despreciable de la cuota y el servicio se recuperó sin intervención.
