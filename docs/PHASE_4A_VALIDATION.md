# Fase 4A — Dashboard React

Fecha: 2026-10-14. Estado: **READY FOR AUDIT**, con revisión visual/interactiva
en navegador pendiente por disponibilidad del entorno. No hubo commit ni push.

## Alcance implementado

Dashboard React + TypeScript + Vite conectado a los endpoints existentes y
PostgreSQL. Sin cambios de backend, migraciones, imports ni nuevas dependencias.
No incluye oportunidades 3B, IA, alertas ni otros módulos.

La interfaz usa fondo oscuro, acentos oro/bronce, tipografías del sistema, CSS
responsive y SVG local. No utiliza imágenes, logos, fuentes remotas o assets
externos. El gráfico SVG evita una dependencia adicional para una serie cuyo
contrato limita el máximo a 366 posiciones.

## Inspección previa y decisiones

- Git inicial limpio, rama `main`, alineada con `origin/main`.
- Leídos README, ARCHITECTURE, ROADMAP y código de endpoints/contratos,
  ventanas, calidad, servicio y migración parcial 003.
- Frontend previo: pantalla de salud; React 18, TypeScript, Vite 6 y lock existente.
- URL: `VITE_API_BASE_URL`, default `http://localhost:8000`, pública en el bundle.
- OpenAPI real inspeccionado desde FastAPI. `/market` declara modelos de
  respuesta; `/partial/markets` y `/partial/items` no los declaran. Sus campos
  provienen del SELECT y migración existentes, comprobados en respuestas reales.
- Catálogo parcial: `id`, `item_key`, `external_item_id`, `key_kind`. No hay
  nombres/calidades. La UI no agrega nombres ficticios ni consulta el catálogo
  independiente de snapshots para completar identidades parciales.
- Dataset y región pertenecen al mercado. La fuente/tipo, base y modo se
  descubren para el item completo, sin fusionar contextos.
- `export_id` requiere elección explícita. Ni ID ni recepción definen cuál es
  la última observación. No se solicita `/partial/imports` para elegir un export.
- CORS real comprobado: `http://localhost:5173` autorizado; `127.0.0.1:5173` no
  autorizado por la configuración actual. Vite/documentación usan localhost
  y puerto fijo; no fue necesario modificar FastAPI o su configuración privada.

## Pantallas y comportamiento

Un dashboard con catálogo lateral y panel de análisis:

1. Dataset → mercado/región → búsqueda local por ID/variante sobre catálogo
   paginado completo → selección de item.
2. Fuente/tipo → accumulated/export → base temporal → export_id si corresponde.
   Cada selector empieza sin selección; no se elige un contexto automáticamente.
3. Ventana: 1..366 buckets observados, rango inclusivo de 1..366 índices, o
   7/14/30 días con base verificada. Índice final opcional en buckets/calendario.
4. Consulta explícita: gráfico de mínimos guardados, promedio, mediana,
   variación porcentual y absoluta, pendiente, mínimo de ventana, último mínimo
   observado y última disponibilidad máxima observada.
5. Cobertura de precio/disponibilidad/eje, advertencias, procedencia y tabla
   expandible por bucket con IDs de evidencia. Null y cero se distinguen.

SIMULATED aparece en dataset, mercado y resultados. Los mínimos acumulados no
se presentan como precios actuales y la disponibilidad no se presenta como ventas.
La tendencia es la pendiente descriptiva de FastAPI, sin recomendaciones.

El eje usa los índices originales. Unknown no se convierte a fecha; una fecha
conocida utiliza `bucket_start` de FastAPI, UTC e índice, nunca `received_at`.
La línea se corta en nulls y saltos de índice. Los puntos admiten foco, teclado
y toque, y la tabla ofrece toda la evidencia sin depender de hover. En móvil el
gráfico admite desplazamiento horizontal para conservar legibilidad.

Los Decimal no pasan por Number. Las etiquetas compactas truncan con `…` y un
control desplegable conserva el valor completo. La conversión monetaria usa
BigInt en la parte entera y preserva el string completo de copper fraccionario.
Las estadísticas se calculan exclusivamente en FastAPI.

Loading, vacío de catálogo/serie/precio, conexión fallida y HTTP 404/409/422/503
tienen estados explícitos y reintento. Timeout por petición: 15 segundos. Cambiar
el contexto/ventana oculta los resultados previos; las peticiones se cancelan y
una respuesta de selección anterior no sustituye la selección vigente.

## Archivos modificados (9)

```text
README.md
docs/ROADMAP.md
frontend/.env.example
frontend/index.html
frontend/package.json
frontend/vite.config.ts
frontend/src/App.tsx
frontend/src/styles.css
frontend/src/api/backend.ts
```

## Archivos nuevos (21)

```text
docs/PHASE_4A_VALIDATION.md
frontend/scripts/generate-api-contracts.py
frontend/scripts/test.mjs
frontend/tsconfig.test.json
frontend/tests/market.test.mjs
frontend/tests/live.test.mjs
frontend/src/api/client.ts
frontend/src/api/contracts.ts
frontend/src/api/generated.ts
frontend/src/api/response-schemas.json
frontend/src/components/MetricCard.tsx
frontend/src/components/StatusPanel.tsx
frontend/src/features/market/ContextControls.tsx
frontend/src/features/market/DataQuality.tsx
frontend/src/features/market/MarketResults.tsx
frontend/src/features/market/PriceChart.tsx
frontend/src/features/market/WindowControls.tsx
frontend/src/features/market/chart.ts
frontend/src/features/market/format.ts
frontend/src/features/market/query.ts
frontend/src/features/market/useResource.ts
```

## Componentes y separación

| Componente/módulo | Responsabilidad |
| --- | --- |
| App | Catálogo, búsqueda, selecciones y coordinación del flujo |
| ContextControls | Fuente/tipo, modo, base y elección explícita de export |
| WindowControls | Restricciones y parámetros de ventana |
| MetricCard / ExactValue | Estado de métrica, muestra, extremos y Decimal exacto |
| PriceChart | SVG, huecos e inspección del bucket |
| DataQuality | Cobertura, advertencias y procedencia |
| MarketResults | Resultado, métricas y tabla de evidencia |
| StatusPanel | Loading, error, vacío y reintento |
| api/client / backend | HTTP paginado, cancelación, errores y URL pública |
| api/contracts / generated / response-schemas | Tipos y compatibilidad runtime |
| format / chart / query | Moneda, geometría y parámetros, sin estadísticas |
| useResource | Estado asíncrono con identidad y descarte de respuestas obsoletas |

## Endpoints utilizados

- `GET /partial/markets`.
- `GET /partial/items?market_id=...&limit=100&offset=...`.
- `GET /market/series?market_id=...&item_key=...&limit=100&offset=...`.
- `GET /market/metrics` con selector y ventana completos.

`/health/db` y `/openapi.json` se usaron solamente para verificación. El frontend
no realiza POSTs. La respuesta de metrics es la única fuente para todas las
estadísticas, puntos y calidad mostrados.

## Validaciones ejecutadas

| Verificación | Resultado |
| --- | --- |
| `npm run build` | Aprobado: TypeScript y Vite producción |
| `npm test` | 15 tests aprobados |
| `npm run test:live` | 3 tests aprobados, FastAPI y PostgreSQL reales |
| Generador de contratos `--check` | Sin drift de OpenAPI |
| Backend `python -m pytest -q -p no:cacheprovider` | 343 tests aprobados |
| Vite y backend iniciados | Frontend HTTP 200, DB reachable |
| CORS con origen localhost:5173 | Autorizado |
| Integridad en verificaciones finales | Conteos, hashes de todas las filas y secuencias iguales entre ambas lecturas |
| `git diff --check` | Sin errores de whitespace |

La suite frontend usa Node test runner, TypeScript y React DOM Server existentes;
no añade un framework. Compila en un directorio temporal propio y lo elimina
validando su ruta. Las fixtures sintéticas solo están en tests y nunca se
importan al bundle. Las pruebas de backend utilizan la base dedicada y esquemas
aislados de la configuración existente. Advertencia preexistente de
Starlette/httpx: una deprecación, sin fallos.

Prueba real de lectura y renderizado React:

```text
PvE · simulation · simulated
item_key: 1900000000
source_id: fresh-seed-340
source_type: simulated
series_mode: accumulated
temporal_basis: unknown
window_type: observed_buckets, size: 30
indices: 2500..2529
mean_daily_minimum_copper: 72.06666666666666666666666666666666666667
median_daily_minimum_copper: 69.5
price_change_copper: -16
price coverage: 30 / 30
```

El test consulta mediante el cliente de la aplicación, valida el contrato y
renderiza MarketResults con esa respuesta real. También consulta rango 0..2:
3 posiciones sin precio, promedio `no_data`, sin reemplazar null por cero.
La ventana 367 devuelve 422 y una fuente inexistente devuelve 404.
Los tests sin DB verifican errores HTTP/conexión, cancelación, paginación,
moneda exacta, tendencias muy pequeñas, huecos, cero, calendario deshabilitado
y elección explícita de export. No equivalen a clicks ni screenshots de navegador.

La comprobación READ ONLY de integridad durante el cierre incluyó 69 agregados
de snapshot, 7 snapshots, 50 items parciales, 4 mercados y 16.628 observaciones
parciales. Los hashes y secuencias coinciden entre las dos lecturas registradas.
No se ejecutaron importaciones ni migraciones sobre desarrollo.

## Limitaciones y revisión pendiente

- La herramienta de UI no expone navegadores: inventario vacío, Chrome e IAB
  indisponibles. Pendiente revisión visual desktop/mobile y flujo mediante clicks,
  teclado y touch. Se verificaron HTTP, componentes renderizados y código
  responsive, sin afirmar que hubo una prueba visual/interactiva.
- La DB existente tiene cero exports/facts/links nativos y base temporal unknown.
  Export y calendario se validaron con fixtures/contratos; no se crearon datos
  para fabricar una prueba live de esos contextos.
- No hay nombres ni búsqueda por nombre: el contrato parcial solo ofrece claves.
  El MVP descarga todas las páginas y filtra localmente; catálogos muy grandes
  necesitarían búsqueda/paginación de interfaz y posiblemente soporte backend.
- IDs BIGINT superiores al entero seguro de JavaScript se rechazan explícitamente
  en la validación de respuesta, evitando una selección con ID redondeado.
- Un deploy/preview requiere URL pública y origen CORS propios; no se incluye
  publicación, autenticación ni configuración privada.
- Validación real de Auctionator/Forever sigue pendiente conforme a 2.5/3A.

Checklist manual para cerrar la revisión visual: abrir `http://localhost:5173`,
elegir simulated → PvE → item 1900000000 → fresh-seed-340 → accumulated → unknown
→ 30 buckets → Consultar histórico; revisar ancho móvil, valores exactos,
foco/tab y tabla. Consultar rango 0..2 para vacío y detener el backend para
verificar error/reintento de conexión.

## Git y dependencias

Rama `main`; 9 archivos modificados y 21 nuevos sin stage. No hay cambios de
backend ni package-lock, secretos o `.env` privados. No se hicieron commits,
pushes, publicaciones o cambios de datos de desarrollo.

Dependencias nuevas: **ninguna**. `package.json` agrega únicamente `test` y
`test:live`. Vite fija host localhost y puerto 5173 con strictPort para el origen
de desarrollo documentado.
