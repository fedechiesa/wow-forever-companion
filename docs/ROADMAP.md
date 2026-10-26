# Roadmap

Este roadmap prioriza aprender rapido y mantener una arquitectura explicable. El objetivo no es construir todas las ideas posibles, sino llegar a una primera version usable de Market Intelligence para el Auction House.

## Prioridad prelaunch — 26/10/2026

Fecha objetivo comunicada para el lanzamiento: **04/11/2026**. El MVP personal
prioriza conservar originales, importar manualmente evidencia validada y consultar
estados económicos auténticos cuando su contexto esté verificado. IA, predicción,
ranking, sincronización automática y ampliaciones de interfaz quedan después.

- **5A.1/5A.2:** archivado local y watcher implementados. Primera prueba con
  `/reload` real aún pendiente; el watcher sólo archiva, no importa.
- **5B.1/5B.1.1:** política de precios extremos, identidad económica y linaje
  implementados en la migración publicada 006. No se modifica 001–006.
- **5B.2 cerrada tras auditoría:** CLI manual de capturas publicadas, preflight
  offline y lectores de mercados/estados/hechos/recepciones v2 validados. Sólo fixtures
  sintéticos y PostgreSQL aislado; sin escrituras en desarrollo ni cambios a
  acumulados 003, frontend o 3A/3B. [Entrega y validación](PHASE_5B2_MANUAL_INGESTION.md).

Antes de usar datos auténticos: revisar evidencia privada de región técnica,
economía/reino o ámbito conectado, alcance compartido/facción, origen, fase y
codec; probar el archivado con el cliente real y acordar una primera importación
manual en laboratorio. Capturas con precios >2147483647 permanecen completas en
el archivo local y bloqueadas para ingestión. Adquisición/recepción no son hora
de scan; varios estados del bucket 2485 no crean varios días de historia.
La aprobación de fixtures no habilita automáticamente una importación auténtica.

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

Estado: implementación completada, auditada y pusheada. La compatibilidad con
SavedVariables auténticos de Forever permanece pendiente y tiene validación separada.

Hardening adversarial: corregidos orden global de locks, retries acotados de 40P01,
coherencia entre batches, rulesets literales, marcador simulado y límites durante
parsing/construcción. Se documenta rechazo de fracciones legítimas ModernAH y el
índice diario fijado en sesión. La decisión aprobada se implementa en 004:
evidencia nativa inmutable separada del acumulado, sin backfill. Los informes de
entrega conservan sus resultados y estados históricos previos a la auditoría/commit.
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

Validación real todavía pendiente:

- Ingerir un archivo SavedVariables auténtico de Auctionator 340 en Forever 1.60.1.
- Confirmar claves de mercado/ruta de AH, codec realmente utilizado y base del reloj.
- Validar comportamiento, cobertura y poda con datos reales.

No se presupone soporte de C_EncodingUtil nativo, ventas ni snapshots completos
a partir de Auctionator. La Fase 3A puede avanzar con simulación sin cerrar estos pendientes.

## Fase 3A: Market Intelligence descriptivo

Estado: implementada; validación y resultados en [PHASE_3A_VALIDATION.md](PHASE_3A_VALIDATION.md).

Objetivo: convertir evidencia parcial compatible en estadísticas revisables.

Entregables:

- Modos accumulated y export explícitos e independientes; 004 vacía soportada.
- Selección por mercado/región/dataset/item completo/fuente/base temporal.
- Mínimo guardado y promedio/mediana de mínimos por bucket observado.
- Variación absoluta/porcentual, desviación muestral, CV y pendiente sobre índices reales.
- Disponibilidad máxima y cambios; sin ventas, demanda, liquidez o volumen transaccionado.
- Ventanas de N buckets de mercado, rangos de índices y 7/14/30 días con base verificada.
- Cobertura, ausencias, muestra, origen l/h_fallback y procedencia desconocida en acumulados.
- GET /market/series y /market/metrics; contratos reutilizables, lectura consistente y Decimal.
- Tests puros y PostgreSQL exclusivamente en testing dedicado/esquemas aislados.

Criterio de salida:

- Podemos reproducir cálculos y revisar los puntos exactos utilizados.
- Reimports y recepción fuera de orden no alteran la unidad de muestra.
- Se distinguen null/zero, índices/calendario y acumulados/exports.
- Los datos y secuencias de Fases 2/2.5 permanecen preservados.

## Fase 3B: Oportunidades explicables

Estado: motor backend 3B.1 publicado; integración UI 3B.2 implementada, pendiente de
captura real y revisión visual. Ranking pendiente.

Objetivo: evaluar reglas simples sobre métricas cuya evidencia pueda revisarse.
3B.1 define cobertura/muestra mínimas configurables y límites de las señales.
Disponibilidad no permite inferir liquidez ni ventas. No usar m
como precio actual ni recepción como cronología del mercado.

Implementado: desviación del último mínimo frente a la mediana anterior,
tendencia con pendiente y cambio de 3A, calidad explícita y razones estructuradas,
contratos Decimal y `GET /market/signals`. El motor no agrega persistencia adicional,
ranking global, predicciones o recomendaciones automáticas complejas.
[Diseño y validación 3B.1](PHASE_3B1_VALIDATION.md).

3B.2 integra las dos señales al análisis del item, después del gráfico, sin
selectores técnicos nuevos ni cambios de backend. Conserva las direcciones del
motor, magnitudes Decimal exactas, evidencia y motivos por regla. Reutiliza la
misma selección/ventana y el scheduler con cancelación; los errores de señales
permiten reintentar sin perder gráfico/métricas. Se verifica que ambas respuestas
describan las mismas observaciones antes de combinarlas. Datos actuales simulados;
la fase permanece abierta para obtener/revisar una captura real.
[Validación 3B.2 y pendiente visual](PHASE_3B2_VALIDATION.md).

## Fase 4: UI usable

Estado: MVP 4A y simplificación 4A.1 implementados; oportunidades y ampliaciones pendientes.
[Validación y límites](PHASE_4A_VALIDATION.md).

Objetivo: tener una experiencia minima para explorar el mercado.

### Fase 4A: primer dashboard React

Implementado:

- React + TypeScript + Vite con estilo dark fantasy responsive, CSS y SVG locales.
- Dataset/mercado/región, búsqueda por ID/variante y catálogo paginado real.
- Descubrimiento paginado de fuentes, modos y bases; selección explícita de export.
- Histórico de mínimos guardados con índices originales y cortes por ausencia.
- Promedio, mediana, cambios, pendiente y disponibilidad provenientes de FastAPI.
- Cobertura, avisos, SIMULATED, trazabilidad por bucket y métricas no calculables.
- Decimal exacto desplegable y conversión monetaria sin pérdida de fracciones.
- Ventanas compatibles con backend, cancelación, loading, error, vacío y reintentos.
- Tipos/esquemas generados desde OpenAPI, validación runtime y tests de frontend.

Verificado: build de producción, tests de precisión/contratos/componentes,
integración de lectura PvE simulado con 30 buckets y estados vacío/404/422.
La revisión visual/interactiva en navegador queda pendiente por disponibilidad
del entorno. La DB local no tiene exports sellados ni bases calendario verificadas;
su selección se valida con fixtures y contratos, conservando los datos existentes.

### Fase 4A.1: navegación simplificada

Implementado sobre 4A sin cambiar backend, contratos, DB o identidad visual:

- Flujo mercado → item → resultados automáticos en una única pantalla.
- Cambio de mercado conservando el item si está disponible en su nuevo catálogo.
- Contexto accumulated único como default seguro; elección explícita para
  múltiples fuentes/bases y para cualquier export, sin ordenar por recepción.
- Ventana inicial de 30 buckets observados; muestras menores conservan avisos.
- Opciones avanzadas colapsadas: dataset, fuente, modo, base temporal,
  exportación, ventanas, cantidad e índices.
- Conservación de filtros explícitos compatibles y restablecimiento con aviso.
- Cancelación, descarte de respuestas antiguas y debounce de edición;
  supresión de requests cancelados por replay de efectos de StrictMode.
- Dispersión y cambios de disponibilidad desplegables, desde métricas de FastAPI.

Correcciones de auditoría: rango inicial inclusivo de hasta 366 posiciones,
inspección SVG por punto más cercano, etiquetas de eje distintas y pruebas de
App montado con jsdom como dependencia de desarrollo, sin nuevo framework.

Validado: 52 tests frontend (42 de contratos/componentes y 10 montados),
4 de integración real de lectura y build de producción. Diseño aprobado en
revisión visual manual. Los tests DOM no incluyen layout real de navegador;
SavedVariables auténticos de Forever sigue sin validación.
[Detalle de 4A.1](PHASE_4A1_VALIDATION.md).

### Alcance total de Fase 4

Entregables previstos:

- Lista/búsqueda por clave y detalle del item: implementados en 4A.
- Histórico de mínimos guardados y disponibilidad máxima, cobertura y calidad: implementados en 4A.
- Filtros por mercado, dataset, fuente, base temporal, modo y ventana: implementados en 4A.
- Panel de oportunidades: pendiente, depende de Fase 3B.

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

- Validación del adaptador Auctionator existente con SavedVariables auténticos.
- Ajustes al contrato normalizado si aparecen campos necesarios.
- Pruebas de evidencia parcial real, rutas AH, codec, reloj, fracciones, cobertura y poda.

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

- Mostrar disponibilidad máxima, buckets con dato, cobertura y procedencia; sin inferir volumen de ventas.
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
