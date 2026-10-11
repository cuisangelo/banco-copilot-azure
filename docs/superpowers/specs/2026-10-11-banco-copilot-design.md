# Banco Copilot Azure — diseño

Proyecto de portfolio: un copiloto cognitivo para asesores de un banco **ficticio**, desplegado en
Azure sobre una suscripción Free Trial (USD 200 / 30 días). Un solo producto que, por dentro, recorre
el temario de la formación: Foundry, Agent Framework, MCP, RAG con AI Search, guardrails, identidad,
observabilidad, evaluación y FinOps.

## Contrato

```
Goal:         Un asesor recibe respuestas sustentadas (requisitos, pasos, citas) sobre productos y
              procedimientos del banco ficticio, o una propuesta de escalamiento cuando la
              información falta o se contradice; desplegado en Azure dentro del crédito Free Trial.
I/O:          Entra: consulta en español del asesor (POST /chat, SSE). Sale: respuesta estructurada
              {requisitos[], pasos[], citas[], estado: ok|aclaracion|insuficiente|contradiccion|
              rechazo} + eventos de traza para el inspector. Frontera pública: copilot-api.
Invariants:   Ninguna afirmación sin cita llega al asesor como "ok". Ningún ticket de escalamiento se
              crea sin aprobación humana explícita. El gasto diario de tokens nunca supera el tope.
              Ninguna credencial vive en código, imagen ni variable de entorno salvo referencias a
              Key Vault.
Security:     Entradas no confiables: texto del asesor, contenido de documentos, respuestas de tools.
              Confía solo en Managed Identity + RBAC. Nunca loguea ni traza RUT, tarjeta, correo ni
              la subscription key de APIM.
Acceptance:   `uv run pytest -q` en verde; `uv run python -m evals.run --target <url>` reporta las
              métricas de la §8 sobre el conjunto de referencia; `scripts/smoke.sh <url>` devuelve
              estado "ok" con ≥1 cita.
Out of scope: Login de usuarios finales, A2A, multimodal, AKS, VNet/Private Endpoints, Redis
              administrado, APIM con MCP nativo, labs/playgrounds separados.
```

## 1. Decisiones tomadas y por qué

| Decisión | Elegido | Alternativa descartada | Motivo |
|---|---|---|---|
| Forma del producto | Un copiloto + inspector plegable | Copiloto + labs | Un producto coherente; la evaluación y la arquitectura viven en el repo/CI |
| Vida de la demo | 30 días de crédito; luego repo + video | Siempre viva | Sin costo post-trial; Terraform permite recrearla |
| Idioma | Todo en español (código en inglés) | Bilingüe | Audiencia LATAM/España |
| Orquestación | Agent Framework propio en Container Apps | Foundry Agent Service | Ingeniería visible: grafo, HITL, tools |
| Gateway | APIM Consumption delante de la API de productos; MCP server propio | APIM Developer con MCP nativo (~USD 48) | MCP nativo no existe en Consumption; USD 0 |
| Región | Canada East | East US 2 / Sweden Central | AI Search Free creable (no "high demand"), groundedness, evaluadores de seguridad y modelos disponibles |
| Modelo de chat | gpt-4.1-mini (GlobalStandard) | gpt-5-mini | Sin tokens de razonamiento: menor latencia y costo predecible |
| Estado | Cosmos DB free tier | Azure Cache for Redis | Redis no tiene nivel gratis; Redis solo en `compose.yaml` local |
| Frontend | React/Vite en Static Web Apps Free + CORS | SWA Standard con backend enlazado (USD 9) | Enlazar backend exige Standard |

Hechos verificados el 2026-10-11 contra la suscripción (no supuestos):

- `quotaId=FreeTrial_2014-09-01`, `spendingLimit=On`.
- Cuota en `canadaeast`, GlobalStandard: `gpt4.1-mini` 200K TPM, `gpt-5-mini` 500K TPM y
  `text-embedding-3-small` 1M TPM.

## 2. Arquitectura

```
Asesor ─▶ SWA (React) ─HTTPS/SSE─▶ copilot-api (ACA, externo)
                                     │  Agent Framework Workflow
                                     ├─▶ Content Safety (Prompt Shields, groundedness)
                                     ├─▶ Foundry / Azure OpenAI (gpt-4.1-mini, embeddings)
                                     ├─▶ AI Search (híbrida + semántica / agentic retrieval)
                                     ├─▶ mcp-products (ACA, interno) ─▶ APIM Consumption ─▶ products-api (ACA)
                                     └─▶ Cosmos DB (sesiones, checkpoints, auditoría)
Ingesta: data/docs ─▶ Blob ─▶ Event Grid ─▶ Function Flex (chunk + embed) ─▶ AI Search
Transversal: Managed Identity (user-assigned), Key Vault, App Insights + Foundry Tracing (OTel),
             ACR Basic, GitHub Actions (OIDC), Terraform, Budget alerts
```

| Componente | Responsabilidad | Depende de |
|---|---|---|
| `services/copilot-api` | FastAPI: `/chat` (SSE), `/escalations/{id}/decision`, tope de tokens, rate limit, workflow | OpenAI, Search, Content Safety, Cosmos, mcp-products |
| `services/mcp-products` | MCP server (streamable HTTP) con tools de solo lectura: `get_product`, `list_products`, `compare_products` | APIM |
| `services/products-api` | API REST simulada de características de productos (tasas, comisiones, requisitos) desde un JSON versionado | — |
| `functions/ingest` | Chunking por sección, embeddings, upsert al índice; disparado por Event Grid | Blob, OpenAI, Search |
| `web/` | Chat, citas clicables, tarjeta de aprobación HITL, inspector plegable | copilot-api |
| `infra/` | Terraform (azurerm + azapi para Foundry) de todo lo anterior | — |
| `data/docs` | 10–15 documentos sintéticos del banco ficticio, dos de ellos contradictorios a propósito | — |
| `evals/` | Conjunto de referencia JSONL, runner, evaluadores | copilot-api desplegado, Foundry |

## 3. Workflow del copiloto

Grafo de Agent Framework (`WorkflowBuilder`), un executor por nodo:

1. **input_guard**: Prompt Shields sobre el texto del asesor. Si detecta un ataque, el estado es `rechazo`.
2. **router**: clasifica la consulta en una de estas rutas:
   - `procedimiento`
   - `producto`
   - `mixta`
   - `fuera_de_alcance`, que lleva a `rechazo`
   - `falta_contexto`, que lleva al clarificador
3. **clarifier**: pide el dato faltante (producto, tipo de cliente) y devuelve el estado `aclaracion`.
   La respuesta del asesor reentra al router con el historial de la sesión.
4. **rag_agent**: búsqueda híbrida más reranking semántico, top-k de chunks con `doc` y `seccion`.
   Antes de entrar al prompt, los chunks pasan por Prompt Shields en modo *documents* (injection
   indirecta).
5. **product_agent**: tool calling vía `MCPStreamableHTTPTool` hacia `mcp-products`. La salida se
   valida con Pydantic.
6. **composer**: arma `{requisitos, pasos, citas}`. Cada afirmación referencia una cita `[doc §seccion]`
   o un dato de producto `[API producto:<id>]`.
7. **verifier**: aplica tres chequeos, en este orden:
   - Groundedness de Content Safety.
   - Cada afirmación tiene cita.
   - Detección de contradicción: mismo atributo con valores distintos entre fuentes.

   Si algún chequeo falla, el estado pasa a `insuficiente` o `contradiccion` y se genera un borrador
   de escalamiento.
8. **escalation (HITL)**: `ctx.request_info()` emite el borrador. El workflow queda en checkpoint
   en Cosmos hasta que el asesor llama a `/escalations/{id}/decision`.
   - Si aprueba, se crea el ticket (simulado) y se audita.
   - Si rechaza, solo se audita.

Cada nodo emite un evento al inspector con:

- nombre del nodo y duración;
- chunks y scores, tool y argumentos;
- capa de guardrail que actuó;
- tokens de entrada y salida, y costo estimado en USD.

## 4. Manejo de errores

- **Recuperación bajo el umbral, o el verificador encuentra afirmaciones sin cita:** el estado es
  `insuficiente`. El copiloto dice qué falta y nunca completa con conocimiento del modelo.
- **Contradicción entre fuentes:** el estado es `contradiccion`, se muestran ambas citas y se propone
  escalar.
- **Falla de products-api o MCP:** se reintenta 2 veces con backoff. Después se responde sin datos de
  producto y se dice explícitamente.
- **429 de OpenAI:** se reintenta según `retry-after`. Agotados los reintentos, se responde un error
  visible, sin degradación silenciosa.
- **Tope diario de tokens alcanzado:** se responde 503 con un mensaje claro. El contador vive en
  Cosmos con clave de fecha UTC.
- **Configuración faltante** (endpoint, nombre de deployment): la app no arranca y falla al iniciar.
  No hay valores por defecto.

## 5. Frontera de seguridad

- **Tools del agente:** son solo de lectura. La única acción con efecto, `create_escalation`, usa
  `approval_mode="always_require"`. Hay un máximo de 5 llamadas a tools por turno.
- **Identidad:** una user-assigned Managed Identity por servicio, con el rol mínimo en cada recurso:
  - *Cognitive Services OpenAI User*
  - *Search Index Data Reader*. La Function de ingesta tiene además *Contributor*.
  - *Cosmos DB Built-in Data Contributor*, limitado al contenedor.
  - *Key Vault Secrets User*.
  - *AcrPull*.
- **Secretos:** hay exactamente dos, y ambos viven en Key Vault, referenciados desde ACA y APIM:
  - la subscription key de APIM, que usa `mcp-products`;
  - el secreto compartido APIM → `products-api`.
- **Red:** `mcp-products` tiene ingress interno al entorno de ACA. APIM inyecta `X-Backend-Secret` con
  una policy `set-header` desde un *named value* respaldado por Key Vault, y `products-api` rechaza
  con 401 cualquier llamada sin esa cabecera. El CORS de
  `copilot-api` solo acepta el dominio de SWA.
- **Superficie pública:** rate limit por IP (10 req/min), tope diario de tokens (configurable,
  requerido) y Budget de Azure con alertas en USD 50 y USD 100.
- **PII:** un filtro de enmascarado (RUT, PAN de tarjeta, correo) sobre logs y atributos OTel antes
  de exportar. Todos los datos son sintéticos.
- **Auditoría:** cada tool call, decisión HITL y rechazo de guardrail se registra en Cosmos
  (`audit`), con id de sesión y de traza.

## 6. Estado y memoria

En Cosmos DB, base `copilot`, se usan tres contenedores:

- `sessions`: historial corto (los últimos N turnos), con partition key `/session_id`.
- `checkpoints`: el estado del workflow pausado por HITL.
- `audit`: el registro de la §5.

La memoria de largo plazo no forma parte del alcance. En desarrollo local, `compose.yaml` levanta el
emulador de Cosmos o Redis; no se usa en Azure.

## 7. Observabilidad y FinOps

- `configure_otel_providers` de Agent Framework más `azure-monitor-opentelemetry` exportan a App
  Insights, conectado al proyecto Foundry para Foundry Tracing.
- Atributos por span (convenciones GenAI de OTel):
  - modelo;
  - tokens de entrada y salida;
  - latencia;
  - `cost_usd_estimate`, calculado con la tabla de precios versionada en `copilot-api`.
- Precios de referencia por 1M de tokens:
  - gpt-4.1-mini: USD 0.40 de entrada y 1.60 de salida.
  - text-embedding-3-small: USD 0.02.
- Un dashboard de workbook en App Insights muestra tokens por día, latencia p50/p95, costo por
  invocación y tasa de rechazos por guardrail.

## 8. Evaluación

`evals/dataset.jsonl` tiene unas 30 filas, cada una con `pregunta`, `tipo`, `respuesta_esperada`,
`citas_esperadas`, `tool_esperada` y `estado_esperado`. Los tipos son:

- respondible
- producto
- mixta
- sin_respuesta
- contradictoria
- fuera_de_alcance
- injection_directa
- injection_indirecta

Métricas:

| Métrica | Cómo |
|---|---|
| Exactitud | LLM-as-a-judge (similarity) contra la respuesta esperada |
| Relevancia de recuperación | Retrieval evaluator de Foundry sobre los chunks devueltos |
| Afirmación ↔ cita | Groundedness evaluator + chequeo determinista de que cada cita esperada aparece |
| Uso correcto de la API | Comparación determinista de tool y argumentos esperados contra los ejecutados |
| Preguntas sin respuesta | El `estado` devuelto coincide con `estado_esperado` (insuficiente o rechazo) |
| Latencia y tokens | p50/p95 y tokens promedio por tipo, leídos de la respuesta |

- **Cuándo corren:** en GitHub Actions, por `workflow_dispatch` y en los PR que tocan `prompts/` o
  `evals/`.
- **Reporte:** se publica como artefacto, y el README enlaza la última corrida.
- **Evaluadores de seguridad:** usan un medidor aparte (USD 20/60 por 1M), así que solo corren de
  forma manual.

## 9. Costos estimados (30 días)

| Concepto | USD |
|---|---|
| Tokens (≈1.000 consultas × ~USD 0,01) | ~10 |
| ACR Basic | ~5 |
| Evaluaciones (calidad + 1–2 corridas de seguridad) | ~3 |
| Content Safety S0, Key Vault, Storage, Event Grid | <1 |
| ACA, AI Search Free, Cosmos Free, SWA Free, APIM Consumption, App Insights (<5 GB), Functions Flex | 0 (cuotas gratis) |
| **Total esperado** | **~20–30 de 200** |

## 10. Riesgos abiertos

- **Functions Flex en Free Trial (confianza media):** si la creación falla, la ingesta pasa a un
  Container Apps Job con el mismo código.
- **Reranking semántico en AI Search Free:** la documentación se contradice. Si no está disponible,
  se queda la búsqueda híbrida sin reranking y se documenta.
- **Agentic retrieval:** la planificación de consultas está en preview (`2026-08-01-preview`). Se usa
  solo si aporta frente a la búsqueda híbrida, medido con las evaluaciones. Si no aporta, no entra.
- **AI Search Free puede eliminarse tras inactividad prolongada:** es aceptable para 30 días.
- **Al terminar el crédito los servicios se deshabilitan:** quedan el repo, el README con capturas,
  el video y `terraform apply` para recrear.

## 11. Arquitectura objetivo de producción (solo documentada)

El README describe qué cambiaría en producción y por qué no se desplegó:

- AKS o ACA dedicado
- VNet con Private Endpoints y DNS privado
- APIM Standard v2 con MCP nativo y `validate-jwt`
- Azure Managed Redis
- Login de asesores con Entra ID
- Content Safety con filtros personalizados
- Evaluación continua en Foundry
