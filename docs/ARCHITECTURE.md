# Arquitectura

## Vision general

WoW Forever Companion se organiza alrededor de un nucleo de Market Intelligence para el Auction House. La aplicacion debe poder cambiar la fuente de datos sin reescribir el analisis, la base de datos ni la experiencia de usuario.

Arquitectura propuesta:

```text
Auction House data source
        |
        v
Ingestion adapter
        |
        v
Normalized snapshot contract
        |
        v
Backend API + domain services
        |
        v
PostgreSQL
        |
        v
React UI / AI assistant tools
```

La parte mas importante es el limite entre `Ingestion adapter` y `Normalized snapshot contract`. Todo lo que venga de Auctionator, otro addon, una API o un archivo exportado debe convertirse a un formato interno comun antes de tocar el resto del sistema.

## Decisiones iniciales

- El backend sera la fuente de verdad del dominio.
- PostgreSQL guardara snapshots historicos y metricas derivables.
- React consumira endpoints del backend; no debe conocer detalles de la fuente de datos.
- La ingestion sera modular: cada fuente tendra un adaptador propio.
- Las oportunidades de mercado empezaran como reglas simples y auditables.
- El asistente de IA no consultara datos crudos directamente; usara herramientas del backend con consultas controladas.

## Decisiones tecnicas de Fase 1

- El frontend se inicializa con React, TypeScript y Vite para mantener una configuracion moderna y pequena.
- El backend se inicializa con FastAPI, `pydantic-settings` para configuracion y `psycopg` para comprobar conexion con PostgreSQL.
- PostgreSQL se prepara para desarrollo local mediante `compose.yaml`, sin dockerizar frontend ni backend.
- La configuracion local usa archivos `.env` ignorados por Git y archivos `.env.example` versionables.
- La base actual no incluye modelos, migraciones ni tablas de dominio.
- La comunicacion minima frontend -> backend usa `GET /health`.
- La comprobacion minima backend -> PostgreSQL usa `GET /health/db`.

## Modulos principales

### Frontend

Responsabilidades:

- Explorar items.
- Mostrar metricas historicas basicas.
- Mostrar oportunidades detectadas.
- Permitir subir o seleccionar datasets simulados en etapas tempranas.
- Consultar al asistente cuando exista la capa de herramientas.

No debe:

- Parsear formatos especificos de addons.
- Implementar reglas de negocio criticas.
- Calcular metricas historicas como fuente de verdad.

### Backend API

Responsabilidades:

- Exponer endpoints para items, snapshots, metricas y oportunidades.
- Validar datos antes de persistirlos.
- Orquestar servicios de ingestion y analisis.
- Exponer herramientas seguras para el asistente de IA.

### Ingestion

Responsabilidades:

- Recibir datos desde una fuente concreta.
- Parsear el formato original.
- Normalizar los datos al contrato interno.
- Registrar errores de importacion y datos incompletos.

Adaptadores previstos:

- `simulated`: datos generados para desarrollo.
- `file_import`: CSV/JSON controlado.
- `auctionator`: futuro adaptador si el formato resulta viable.
- `api`: futuro adaptador si existe una API util.

### Market Intelligence

Responsabilidades:

- Calcular estadisticas por item y ventana temporal.
- Detectar tendencias simples.
- Medir volatilidad.
- Detectar oportunidades iniciales.
- Calcular margenes de crafting cuando existan datos de profesiones y recetas.

En v0.1 se priorizan reglas explicables sobre modelos avanzados.

### AI tools

Responsabilidades futuras:

- Permitir preguntas sobre nuestros datos.
- Traducir consultas del usuario en llamadas controladas al backend.
- Responder con evidencia: item, rango temporal, snapshot y metricas utilizadas.

Ejemplos futuros:

- "Que items bajaron fuerte en las ultimas 24 horas?"
- "Que materiales tienen mayor volatilidad esta semana?"
- "Hay oportunidades de compra por debajo de la media historica?"

## Estructura propuesta del repositorio

Estructura objetivo para cuando se inicialice el proyecto:

```text
wow-forever-companion/
  README.md
  docs/
    ARCHITECTURE.md
    ROADMAP.md
  compose.yaml
  backend/
    app/
      api/
      core/
      db/
      ingestion/
        adapters/
      market/
      ai_tools/
    tests/
  frontend/
    src/
      components/
      pages/
      api/
      features/
        market/
  data/
    samples/
    imports/
  scripts/
```

Responsabilidades previstas:

- `backend/app/api`: endpoints HTTP.
- `backend/app/core`: configuracion y utilidades compartidas.
- `backend/app/db`: modelos, migraciones y acceso a datos.
- `backend/app/ingestion`: contrato normalizado y flujo de importacion.
- `backend/app/ingestion/adapters`: adaptadores por fuente de datos.
- `backend/app/market`: calculo de metricas y oportunidades.
- `backend/app/ai_tools`: herramientas controladas para consultas asistidas por IA.
- `frontend/src/features/market`: pantallas y estado de Market Intelligence.
- `data/samples`: datasets simulados versionables.
- `data/imports`: archivos locales importados, normalmente no versionables.
- `scripts`: comandos auxiliares simples.
- `compose.yaml`: PostgreSQL local para desarrollo.

La Fase 1 implementa el esqueleto tecnico de frontend, backend y configuracion local. Los modulos de dominio siguen vacios a proposito hasta fases posteriores.

## Modelo de datos inicial

Modelo conceptual para v0.1:

### `realms`

Representa el servidor o mercado observado.

Campos iniciales:

- `id`
- `name`
- `region`
- `created_at`

### `items`

Catalogo normalizado de items.

Campos iniciales:

- `id`
- `external_item_id`
- `name`
- `quality`
- `item_class`
- `item_subclass`
- `created_at`

`external_item_id` debe ser estable si la fuente lo provee. Si no existe, se debera definir una estrategia temporal y marcarla como pendiente de validacion.

### `auction_snapshots`

Representa una captura del Auction House para un realm y una fuente.

Campos iniciales:

- `id`
- `realm_id`
- `source_type`
- `source_version`
- `captured_at`
- `imported_at`
- `raw_reference`

### `auction_snapshot_items`

Agregado por item dentro de un snapshot. En v0.1 conviene guardar datos agregados antes que cada subasta individual, salvo que la fuente real obligue a conservar granularidad completa.

Campos iniciales:

- `id`
- `snapshot_id`
- `item_id`
- `min_buyout`
- `avg_buyout`
- `max_buyout`
- `quantity_total`
- `auction_count`

### `market_metrics`

Metricas calculadas para un item, realm y ventana temporal.

Campos iniciales:

- `id`
- `realm_id`
- `item_id`
- `window`
- `calculated_at`
- `min_price`
- `avg_price`
- `max_price`
- `median_price`
- `volume_total`
- `volatility`
- `trend`

Estas metricas pueden recalcularse. La persistencia se justifica cuando haga mas simple consultar historicos o alimentar la UI.

### `market_opportunities`

Senales detectadas por reglas explicables.

Campos iniciales:

- `id`
- `realm_id`
- `item_id`
- `detected_at`
- `opportunity_type`
- `score`
- `reason`
- `reference_price`
- `current_price`
- `status`

## Contrato de snapshot normalizado

Todo adaptador debe producir una estructura equivalente a:

```json
{
  "realm": "Example Realm",
  "source_type": "simulated",
  "source_version": "0.1",
  "captured_at": "2026-10-05T00:00:00Z",
  "items": [
    {
      "external_item_id": "12345",
      "name": "Copper Ore",
      "quality": "common",
      "min_buyout": 120,
      "avg_buyout": 150,
      "max_buyout": 220,
      "quantity_total": 430,
      "auction_count": 37
    }
  ]
}
```

Los precios deben guardarse como enteros en la unidad minima disponible, por ejemplo copper, para evitar errores de punto flotante.

## Flujo de ingestion

1. La fuente entrega un snapshot o export.
2. El adaptador correspondiente parsea el formato original.
3. El adaptador valida campos obligatorios.
4. El adaptador convierte los datos al contrato normalizado.
5. El backend persiste `auction_snapshots` y `auction_snapshot_items`.
6. El servicio de Market Intelligence recalcula metricas afectadas.
7. El sistema detecta oportunidades segun reglas activas.
8. La UI y las herramientas de IA consultan datos ya normalizados.

## Reglas iniciales de oportunidades

Para v0.1, las reglas deben ser simples:

- Precio actual por debajo de un porcentaje configurable de la media historica.
- Volumen suficiente para evitar senales sobre datos demasiado chicos.
- Caida brusca respecto de snapshots recientes.
- Alta volatilidad marcada como riesgo, no necesariamente como oportunidad.

Cada oportunidad debe incluir una razon legible para poder defenderla.

## Riesgos tecnicos

### Fuente de datos del Auction House

Es el mayor riesgo del proyecto. Todavia no sabemos si existira API, si un addon exportara datos suficientes, que granularidad tendremos ni con que frecuencia podremos actualizar.

Mitigacion:

- Disenar adaptadores intercambiables.
- Trabajar primero con contrato normalizado.
- Mantener datasets simulados.
- Documentar cada supuesto de la fuente real.

### Identidad de items

Si no hay IDs estables, comparar historicos puede ser fragil.

Mitigacion:

- Preferir `external_item_id` cuando exista.
- Evitar depender solo del nombre.
- Registrar la fuente y version del dato.

### Calidad y frecuencia de snapshots

Snapshots incompletos o poco frecuentes pueden producir metricas enganadoras.

Mitigacion:

- Guardar `captured_at` e `imported_at`.
- Mostrar volumen y cantidad de observaciones.
- No generar oportunidades cuando la muestra sea insuficiente.

### Complejidad prematura

El proyecto puede crecer hacia muchas areas de WoW.

Mitigacion:

- Mantener v0.1 centrada en Market Intelligence.
- Posponer personajes, guilds, raids y gear planning.
- Evitar microservicios y pipelines complejos al inicio.

## Cosas que no deberiamos construir todavia

- Integraciones definitivas con addons sin validar formato real.
- Prediccion avanzada de precios.
- Optimizacion automatica de trading.
- Sistema completo de profesiones.
- Gestion de personajes.
- Guild roster.
- Raid planner.
- Gear planner.
- Autenticacion compleja.
- Multi-tenant o roles avanzados.
- Infraestructura cloud elaborada.
