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

Objetivo: crear el esqueleto del proyecto sin construir funcionalidades avanzadas.

Entregables previstos:

- Backend FastAPI inicial.
- Frontend React inicial.
- PostgreSQL local.
- Configuracion basica de entorno.
- Health checks.
- Convenciones de estructura del repo.

Criterio de salida:

- La app corre localmente.
- Backend, frontend y database estan conectados de forma basica.
- No hay todavia dependencia de una fuente real del Auction House.

## Fase 2: Datos simulados e ingestion controlada

Objetivo: validar el flujo de ingestion sin esperar la fuente real.

Entregables previstos:

- Generador de snapshots simulados.
- Importador de archivo JSON o CSV controlado.
- Contrato normalizado de snapshot.
- Persistencia de realms, items, snapshots y agregados por item.
- Registro basico de errores de importacion.

Criterio de salida:

- Podemos cargar multiples snapshots.
- Podemos consultar historicos por item.
- La fuente de datos esta desacoplada mediante adaptadores.

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
