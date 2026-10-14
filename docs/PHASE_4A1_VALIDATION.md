# Fase 4A.1 — Simplificación del dashboard

Fecha: 2026-10-14. **READY TO COMMIT** tras correcciones finales de auditoría.
Implementación local sobre 4A sin commit ni push. Diseño aprobado por revisión
visual manual del usuario; interacción montada cubierta ahora con jsdom.

## Flujo principal

Una pantalla: elegir mercado → buscar/seleccionar item → resultados automáticos.
Se conserva el diseño dark fantasy, gráfico SVG, tarjetas, cobertura, avisos y
procedencia. El área principal de exploración tiene mercado y búsqueda, sin
paso previo de dataset ni botón obligatorio de consulta.
Cambiar mercado conserva el item si el nuevo catálogo lo admite y actualiza
automáticamente su análisis; si no está disponible, lo limpia con aviso.

Cada mercado se identifica por su ID de API. Se muestran `market_key`, región,
reglas si difieren de la clave y SIMULATED/REAL. PvE/PvP/HC/RP no se interpretan
como nombres de reinos. El catálogo sigue usando la clave completa del item,
sin nombres/iconos de WoW inventados. ItemList admite una función de etiqueta
para incorporar información verificada en otra fase sin cambiar la identidad.

## Selección predeterminada y conservación

1. Sin elección previa: priorizar accumulated. Si solo queda un contexto
   accumulated completo, consultarlo; si quedan varias fuentes o bases,
   pedir elección explícita. El orden de API no decide el resultado.
2. Solo exports: pedir elegir uno, incluso si existe uno solo. No se ordenan
   por recepción ni se interpreta el ID como cronología de observación.
3. Ventana inicial: 30 buckets observados del mercado, también con base conocida.
   Es un criterio uniforme que no presupone fechas actuales ni 30 días continuos.
   La falta de buckets conserva las advertencias/cobertura de FastAPI.
4. Las preferencias explícitas se conservan cuando siguen disponibles para el
   nuevo item/mercado. Una selección automática no se promueve a preferencia
   explícita para resolver silenciosamente la ambigüedad de un item posterior.
5. Fuente/modo/base incompatibles se restablecen con aviso. Un export incompatible
   se borra y requiere otra elección. Calendario con nueva base unknown pasa a
   30 buckets observados con aviso. Rangos/buckets compatibles se conservan.
6. El filtro de dataset vive en Opciones avanzadas. Al inicio incluye todos los
   mercados. Si excluye el mercado actual, se vacía la selección con aviso y se
   pide elegir otro mercado, sin cambiar automáticamente de identidad.

## Opciones avanzadas

Un `details` nativo, inicialmente cerrado, contiene dataset, fuente/source_id,
modo accumulated/export, base temporal, export específico y controles completos
de ventana (tipo, cantidad, índices inicial/final y 7/14/30 días verificados).
Los términos técnicos incluyen explicación breve. Todos los cambios válidos
consultan automáticamente; los parámetros inválidos muestran error y no consultan.

Mercado, dataset, fuente/tipo, modo/base y export se mantienen explícitos en
cada query interna. No se suman ni mezclan series. La fuente y base siguen
visibles en el resumen, y SIMULATED permanece en mercado y resultados.

## Interacción y datos

El plan de análisis deriva del contexto y ventana actuales. Al cambiar item,
mercado o contexto se ocultan inmediatamente las métricas anteriores. Cada
petición cancelada pierde la capacidad de publicar éxito o error. Un debounce
de 200 ms evita consultas por cada valor intermedio al editar una ventana;
cancelar el primer efecto de StrictMode antes de su microtarea evita ese request.

Se conservaron gráfico, Decimal exacto, moneda con BigInt, ceros y ausencias,
índices sin fechas falsas, disponibilidad sin ventas, avisos y evidencia por
bucket. Se añadió una sección desplegable de dispersión (desviación muestral/CV)
y cambios de disponibilidad usando exclusivamente métricas existentes de FastAPI.
No se alteró ningún algoritmo estadístico.

## Archivos de esta iteración

Modificados sobre el trabajo local de 4A:

```text
README.md
docs/ROADMAP.md
frontend/src/App.tsx
frontend/src/styles.css
frontend/src/features/market/ContextControls.tsx
frontend/src/features/market/MarketResults.tsx
frontend/src/features/market/useResource.ts
frontend/tsconfig.test.json
frontend/tests/market.test.mjs
frontend/tests/live.test.mjs
```

Nuevos en 4A.1:

```text
docs/PHASE_4A1_VALIDATION.md
frontend/src/features/market/AdvancedOptions.tsx
frontend/src/features/market/ContextChoice.tsx
frontend/src/features/market/ItemList.tsx
frontend/src/features/market/selection.ts
frontend/src/features/market/resource.ts
```

No se hicieron resets ni checkouts destructivos. Se conserva la implementación
4A en el working tree; su informe original documenta esa entrega histórica.
Sin cambios de backend, PostgreSQL, migraciones, API, algoritmos ni dependencias.

## Validaciones originales de 4A.1

- `npm test`: **29 tests aprobados** (15 anteriores y 14 de selección/interacción).
- `npm run test:live`: **4 tests aprobados** con FastAPI y PostgreSQL activos.
- `npm run build`: TypeScript y Vite producción aprobados.
- Generador de contratos `--check`: sin drift.
- Frontend local HTTP 200 y `/health/db` reachable.
- `git diff --check`: sin errores de whitespace.
- Integridad PostgreSQL en READ ONLY antes/después de 4A.1: conteos, hashes de
  todas las filas y secuencias de desarrollo coincidentes.

Prueba real: PvE simulado → primer item disponible 1900000000 → resolver seguro
→ plan inicial → scheduler automático → `/market/metrics` → renderizado React.
Resultado: 30 buckets, promedio string
`72.06666666666666666666666666666666666667` copper, mediana `69.5`, cobertura 30/30
y SIMULATED visible. También se comprobaron rango vacío 0..2, 404 y 422.
Otra prueba consulta el mismo item en un segundo mercado existente, verifica
su contexto propio y la ventana de 30 buckets, sin mezclar ambas respuestas.

Los tests adicionales cubren defaults independientes del orden de API,
ambigüedad de fuentes/bases, no auto-export, filtros compatibles entre items,
resets de fuente/calendario/export, defaults que no se vuelven preferencias,
avanzadas cerradas, labels, carga sin submit, carreras con éxito/error obsoleto,
cancelación StrictMode/debounce y ocultamiento inmediato de datos de otro item.

Estas pruebas utilizan el resolver y scheduler consumidos por React, y
renderizado de componentes con React DOM Server. No equivalen a clicks de un
navegador; esa revisión manual sigue pendiente.

## Limitaciones

- No hay navegador disponible en la herramienta de UI. Pendiente verificar
  layout/interacción en dispositivos reales. El diseño tiene aprobación visual
  manual y los eventos React montados tienen pruebas DOM, con CTM controlada.
- La DB existente sigue sin exports sellados o calendario verificado; esas
  variantes se validan con fixtures, sin importar ni fabricar datos.
- Búsqueda local por ID/variante; nombres reales dependen de un catálogo futuro.
- SavedVariables auténticos de Forever continúa pendiente, sin nueva afirmación
  de compatibilidad. 3B, IA, alertas, autenticación y catálogos externos no se
  implementan en esta iteración.

Checklist UX: elegir PvE SIMULATED → item → observar carga automática; abrir
Opciones avanzadas, cambiar cantidad y cambiar de item; comprobar que los
filtros válidos persisten. Probar rango 0..2 y desconexión/reintento. Cuando haya
varias series/exports reales, comprobar la elección explícita correspondiente.

## Git final

Estado histórico de la entrega 4A.1: `main`, 9 archivos modificados y 27 nuevos
sin stage. El estado tras correcciones finales se registra a continuación.

## Correcciones finales de auditoría

Se resolvieron los dos MEDIUM y los dos LOW sin ampliar el dashboard:

- Rango inicial: `max(primer índice, último índice - 365)..último índice`.
  Regresiones para 1, 30, 366 y 501 índices, además de índices no consecutivos.
  Para 0..500, el default pasa a 135..500 (366 posiciones). Los rangos explícitos
  se validan como antes y nunca se recortan silenciosamente.
- Inspección SVG: un handler de Pointer Events calcula coordenadas locales
  mediante la inversa de screen CTM y selecciona el precio más cercano. Los
  empates usan el menor índice. Las posiciones null quedan excluidas y los ceros
  se conservan. Los círculos de foco no capturan pointer events; teclado y tabla
  mantienen la selección exacta. Los casos de 30 y 366 puntos incluyen precios
  repetidos, cercanía entre puntos y eventos mouse/touch en componentes montados.
- Eje vertical: ticks copper enteros distintos en pasos 1/2/5 por orden de
  magnitud, evitando redondear niveles diferentes a la misma etiqueta. Precios
  constantes siguen siendo una línea horizontal. Cero ya no genera 1/1/0/0.
- Cobertura montada: el App real y su cliente API se compilan con Vite para tests;
  solo la URL del backend se sustituye por un mock de respuestas. Se usa React
  StrictMode, createRoot y act, con eventos DOM sobre los controles reales.

Nueva dependencia únicamente de desarrollo: `jsdom 26.1.0`, compatible con el
Node 20.12 instalado (engines >=18). Justificación: no había una implementación
DOM para montar App. No se añadieron Vitest, Testing Library, otro runner ni
bibliotecas de gráficos. El lock agrega solo jsdom y sus dependencias; npm
informó una deprecación de whatwg-encoding, transitiva y usada solo en tests.
Metadatos: [npm jsdom 26.1.0](https://registry.npmjs.org/jsdom/26.1.0).

Archivos afectados por estas correcciones:

```text
README.md
docs/ROADMAP.md
docs/PHASE_4A1_VALIDATION.md
frontend/package.json
frontend/package-lock.json
frontend/scripts/test.mjs
frontend/src/features/market/WindowControls.tsx
frontend/src/features/market/PriceChart.tsx
frontend/src/features/market/chart.ts
frontend/tests/market.test.mjs
frontend/tests/app.test.mjs (nuevo)
```

Validación final:

- 42 tests de funciones/componentes/contratos y 10 tests montados: **52 aprobados**.
- 4 tests de integración de lectura con FastAPI/PostgreSQL: aprobados; las
  métricas PvE conservan promedio 72.06666666666666666666666666666666666667 copper,
  mediana 69.5 y cobertura 30/30. Vacío, cambios de mercado y 404/422 sin regresión.
- Build TypeScript/Vite producción aprobado y contratos OpenAPI sin drift.
- App montado verifica mercado/item, carga sin submit y sin request duplicado
  en StrictMode, apertura/cierre de avanzadas, ocultamiento de datos anteriores,
  métricas/discovery fuera de orden, loading, catálogo vacío, error/reintento,
  respuesta sin precios y filtros compatibles entre items.
- `git diff --check` sin errores; ningún cambio de backend o contratos generados.
- PostgreSQL: hashes de todas las filas, conteos y secuencias coinciden con la
  lectura READ ONLY previa a esta corrección. No hubo imports ni migraciones.

Limitaciones: jsdom no dibuja ni calcula layout; los tests SVG proporcionan una
CTM de escala/traslación conocida. Las pruebas en dispositivos físicos y los
exports/calendario reales siguen siendo independientes de esta cobertura.

Git final: `main`, 10 archivos modificados y 28 nuevos sin stage, acumulando
4A/4A.1 y las correcciones. Sin commit ni push.
