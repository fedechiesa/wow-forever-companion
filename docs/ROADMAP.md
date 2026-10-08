# Roadmap

Este roadmap prioriza aprender rapido y mantener una arquitectura explicable. El objetivo no es construir todas las ideas posibles, sino llegar a una primera version usable de Market Intelligence para el Auction House.

## Fase 0: Definicion inicial

Estado: documentacion inicial.

Objetivos:

- Definir alcance de v0.1.
- Acordar arquitectura general.
- Identificar riesgos de datos del Auction House.
- Definir modelo de datos inicial.
- Separar claramente fuente de datos, dominio, UI y futuras herramientas de IA.

Entregables:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

## Fase 0.5: Data Source Research

Estado: puede realizarse en paralelo al desarrollo.

Objetivo: investigar tempranamente posibles fuentes reales de datos del Auction House sin acoplar todavia la implementacion a ninguna de ellas.

Fuentes a investigar:

- Auctionator.
- SavedVariables de addons.
- Exports manuales o generados por addons.
- Otros addons de Auction House.
- APIs disponibles para WoW Forever, si existieran.

Preguntas a responder:

- Que campos reales podemos obtener por item y por subasta.
- Si existe un identificador estable de item.
- Si los datos incluyen buyout, bid, cantidad, stacks, vendedor, timestamp o realm.
- Que granularidad tendremos: subasta individual o agregado por item.
- Con que frecuencia se pueden obtener snapshots.
- Que tan automatizable es el flujo sin violar restricciones tecnicas o terminos de uso.
- Que limitaciones tienen los formatos de export o SavedVariables.

Entregables previstos:

- Notas de investigacion sobre cada fuente evaluada.
- Ejemplos pequenos de datos reales o representativos, cuando esten disponibles.
- Recomendacion inicial de fuente preferida.
- Lista de ajustes necesarios al contrato normalizado, si aparecen.
- Riesgos actualizados sobre disponibilidad, calidad y frecuencia de datos.

Criterio de salida:

- Los supuestos del contrato normalizado quedan validados o marcados para correccion antes del lanzamiento de WoW Forever.
- El desarrollo puede seguir usando datos simulados sin depender todavia de una fuente real.
- No se implementa una integracion definitiva en esta fase.

## Fase 1: Base tecnica minima

Estado: completada. Validada localmente con PostgreSQL en Docker, backend FastAPI y frontend React/Vite.

Objetivo: crear el esqueleto del proyecto sin construir funcionalidades avanzadas.

Entregables previstos:

- Backend FastAPI inicial. Completado.
- Frontend React inicial. Completado.
- PostgreSQL local. Completado y verificado con `compose.yaml`.
- Configuracion basica de entorno. Completado con `.env.example` versionables.
- Health checks. Completado con `/health` y `/health/db`.
- Convenciones de estructura del repo. Completado.

Criterio de salida:

- La app corre localmente. Verificado para backend y frontend.
- Backend, frontend y database estan conectados de forma basica. Verificado frontend -> backend y backend -> PostgreSQL.
- No hay todavia dependencia de una fuente real del Auction House. Completado.

## Fase 2: Datos simulados e ingestion controlada

Estado: completada y revalidada tras auditoria tecnica. Verificados migraciones SQL incrementales, snapshots JSON simulados, idempotencia secuencial/concurrente, identidad completa de realm y endpoints historicos contra PostgreSQL.

Objetivo: validar el flujo de ingestion sin esperar la fuente real.

Entregables previstos:

- Snapshots simulados versionables. Completado con archivos JSON en `data/samples/`.
- Importador de archivo JSON controlado. Completado con `FileAdapter` y scripts locales.
- Contrato normalizado de snapshot. Completado con modelos Pydantic.
- Persistencia de realms, items, snapshots y agregados por item. Completado con migraciones SQL.
- Registro basico de errores de importacion. Completado con `import_runs`.
- Contratos alineados con PostgreSQL INTEGER y timestamps con timezone normalizados a UTC. Completado.
- Tests de integracion aislados en una base dedicada y un esquema propio por test. Completado con proteccion contra apuntar a desarrollo.

Criterio de salida:

- Podemos cargar multiples snapshots. Verificado con 7 snapshots simulados.
- Podemos consultar historicos por item. Verificado con `GET /items/{item_id}/history`.
- La fuente de datos esta desacoplada mediante adaptadores. Completado con contrato de adapter y `FileAdapter`.
- Dos importaciones concurrentes del mismo snapshot devuelven completed y duplicate con el mismo ID, sin 500. Verificado con servidor HTTP real y tests de regresion.
- Realms homonimos de distinta region no se mezclan en historicos. Verificado por realm_id y nombre/region; selectores ambiguos devuelven 422.
- Suite final: 88 tests aprobados, incluida lectura fisica de JSON, rollback intermedio, limites numericos, timezone, migracion de regiones e idempotencia entre archivo y HTTP.
- Datos y secuencias de desarrollo permanecen iguales antes/despues de la suite. Verificado con cantidades y hash de los registros; los esquemas temporales se eliminaron.

## Fase 2.5: Auctionator Integration & Fresh Market Simulation

Estado: implementación y validación con fixtures/PostgreSQL realizadas;
**pendiente de validación con SavedVariables real de Forever**. No se marca completa.

Hardening adversarial: corregidos orden global de locks, retries acotados de 40P01,
coherencia entre batches, rulesets literales, marcador simulado y límites durante
parsing/construcción. Se documenta rechazo de fracciones legítimas ModernAH y el
índice diario fijado en sesión. La decisión aprobada se implementa en 004:
evidencia nativa inmutable separada del acumulado, sin backfill. Sigue pendiente
recibir los payloads exactos de la auditoría para comparar la reproducción de
deadlock; la regresión construida reproduce y corrige el mecanismo.
Ver [informe de hardening](PHASE_25_HARDENING.md).

Entregables implementados:

- Inspección de Auctionator 340 externo, sin copiar ni modificar el addon.
- Contrato Pydantic de evidencia parcial, separado de snapshots completos.
- Parser de literales Lua y subconjunto LibCBOR comprobado, con límites y sin ejecución.
- Adapter sin dependencia de PostgreSQL y servicio transaccional con trazabilidad.
- Migración incremental 003: mercados, catálogo parcial, observaciones e imports.
- Migración incremental 004: exports, hechos l/h/a/m y vínculos de recepción;
  consulta explícita por export_id sin cambiar los acumulados ni Fase 2.
- Identidad por mercado/dataset/item/fuente/base temporal/día/estadística; variantes
  de items preservadas y últimos mínimos tratados como evidencia sin fecha.
- CLI de importación y endpoints mínimos de imports, mercados, items e histórico.
- Generador seed 340: 50 items ficticios, 30 días, cuatro mercados y 16.628
  estadísticas simuladas, incluyendo ausencias y apariciones tardías.
- Tests unitarios, validación HTTP y PostgreSQL aislado; reimportación y
  persistencia física verificadas conservando datos y secuencias de Fase 2.
- Documentación de [formatos/semántica](AUCTIONATOR_340.md) y
  [validación inicial](PHASE_25_VALIDATION.md) y
  [evidencia por exportación](PHASE_25_EXPORT_EVIDENCE.md).

Criterio de salida todavía pendiente:

- Ingerir un archivo SavedVariables auténtico de Auctionator 340 en Forever 1.60.1.
- Confirmar claves de mercado/ruta de AH, codec realmente utilizado y base del reloj.
- Validar comportamiento, cobertura y poda con datos reales.

No se presupone soporte de C_EncodingUtil nativo, ventas ni snapshots completos
a partir de Auctionator. Fase 3 no se inició en este trabajo.

## Fase 3: Market Intelligence v0.1

Objetivo: convertir historicos en informacion util.

Entregables previstos:

- Metricas por item y ventana temporal.
- Minimo, promedio, maximo, mediana, volumen y volatilidad.
- Tendencia simple.
- Reglas iniciales de oportunidades.
- Razones explicables para cada oportunidad.

Criterio de salida:

- Podemos identificar items con cambios relevantes de precio.
- Las oportunidades muestran evidencia suficiente para ser revisadas manualmente.
- Las reglas son simples de explicar y ajustar.

## Fase 4: UI usable

Objetivo: tener una experiencia minima para explorar el mercado.

Entregables previstos:

- Lista/busqueda de items.
- Vista de detalle de item.
- Historico de precios y volumen.
- Panel de oportunidades.
- Filtros por realm, ventana temporal y tipo de oportunidad.

Criterio de salida:

- Un usuario puede investigar un item sin tocar la base de datos.
- Un usuario puede revisar oportunidades desde la interfaz.

## Fase 5: Herramientas para asistente de IA

Objetivo: consultar datos propios mediante herramientas controladas.

Entregables previstos:

- Herramientas backend para busqueda de items.
- Herramientas para metricas historicas.
- Herramientas para oportunidades.
- Respuestas con evidencia y parametros consultados.

Criterio de salida:

- El asistente puede responder preguntas de mercado usando nuestros datos.
- Las respuestas no dependen de inventar informacion fuera de la base.

## Fase 6: Validacion con fuente real

Objetivo: reemplazar o complementar los datos simulados con datos reales usando lo aprendido en la Fase 0.5.

Entradas esperadas:

- Fuente candidata recomendada.
- Ejemplos de datos reales o representativos.
- Supuestos del contrato normalizado ya validados o corregidos.
- Riesgos conocidos de frecuencia, granularidad y calidad.

Entregables previstos:

- Adaptador para la fuente elegida.
- Ajustes al contrato normalizado si aparecen campos necesarios.
- Pruebas con snapshots reales.

Criterio de salida:

- El sistema ingiere datos reales sin cambiar el nucleo de analisis.
- Los supuestos de v0.1 quedan validados o corregidos.

## Fase 7: Primera version usable

Objetivo: tener una herramienta que realmente sirva jugando.

Entregables previstos:

- Ingestion repetible.
- Historicos confiables.
- UI de investigacion de mercado.
- Oportunidades revisables.
- Consultas asistidas por IA sobre datos propios.
- Documentacion suficiente para explicar decisiones tecnicas en portfolio.

Criterio de salida:

- Podemos usar WoW Forever Companion para tomar decisiones basicas de compra, venta o seguimiento de items.

## Funcionalidades futuras

Estas areas pueden existir mas adelante, pero no deben competir con Market Intelligence durante v0.1:

- Personajes.
- Guild y roster.
- Raid planner.
- Profesiones completas.
- Gear y loot planning.
- Crafting avanzado.
- Alertas en tiempo real.
- Deploy publico.
- Autenticacion multiusuario.

## Riesgos principales

### Obtencion de datos del Auction House

El proyecto depende de datos que todavia no sabemos como obtener. Este riesgo puede afectar frecuencia de actualizacion, campos disponibles, precision de precios y granularidad.

Respuesta del roadmap:

- Empezar con datos simulados.
- Definir contrato normalizado temprano.
- Encapsular cada fuente en adaptadores.
- Validar la fuente real antes de construir features dependientes de ella.

### Datos insuficientes para senales confiables

Una oportunidad basada en pocos snapshots puede ser enganosa.

Respuesta del roadmap:

- Mostrar volumen y cantidad de observaciones.
- Aplicar umbrales minimos.
- Marcar senales como sugerencias, no como certezas.

### Scope creep

WoW ofrece muchas areas tentadoras para construir.

Respuesta del roadmap:

- La primera version usable se define por inteligencia de mercado, no por cobertura completa del juego.
- Las features secundarias se documentan como futuras, no como parte de v0.1.

## No construir todavia

- Integracion final con Auctionator antes de validar formato y disponibilidad.
- Sistemas de personajes, guild o raids.
- Planificador completo de profesiones.
- Recomendaciones automaticas complejas.
- Machine learning de prediccion.
- Arquitectura distribuida.
- Microservicios.
- Permisos avanzados.
- Deploy cloud complejo.
