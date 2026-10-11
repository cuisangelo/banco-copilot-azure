# Cobertura del temario

**Leyenda:**

- ✅ hecho y verificado ejecutándolo (en vivo o con tests);
- ⚠️ configurado pero no verificado, o hecho solo en parte;
- ❌ no está.

Estado al 2026-10-11, después de la evaluación 4.

| Área | Ítem | Estado | Dónde / evidencia |
|---|---|---|---|
| **Lenguaje & Development** | Python ≥ 3.12 + librerías | ✅ | Monorepo con uv; 220 tests |
| | Jupyter Notebooks | ❌ | No hay notebooks; la evaluación es un script (`evals/run.py`) |
| | SDKs de Azure / Foundry | ✅ | `azure-identity`, `azure-search-documents`, `azure-cosmos`, `azure-ai-evaluation`, `azure-monitor-opentelemetry` |
| **AI Platform & Models** | Microsoft Foundry | ✅ | Recurso AIServices + proyecto `bcopilot-project` (Terraform) |
| | Azure OpenAI / LLMs | ✅ | `gpt-4.1-mini` GlobalStandard; responde en vivo |
| | Embeddings | ✅ | `text-embedding-3-small`; 12 documentos indexados |
| | Modelos multimodales | ❌ | Solo texto |
| **Agentic AI** | Microsoft Agent Framework | ✅ | 1.21, `WorkflowBuilder` con 9 executors |
| | Agents | ⚠️ | Executors especializados con salida estructurada; no hay agentes con tool calling libre (decisión: la identidad y el límite de 5 llamadas viven en código) |
| | Multi-Agent | ⚠️ | Grafo secuencial de roles (router, RAG, productos, cliente, composer, verificador); no implementa los patrones supervisor ni concurrente |
| | Tools | ✅ | 5 tools vía MCP (productos y cliente) |
| | Workflows | ✅ | Grafo, HITL con `request_info` y checkpoints persistidos en Cosmos; verificado en vivo con aprobación + reanudación |
| | Context Engineering | ✅ | Fuentes numeradas S1…Sn, historial con nivel 2 redactado, prompts versionados |
| **Knowledge & Retrieval** | Azure AI Search | ✅ | Nivel Free, índice `bank-docs` |
| | Vector / Hybrid / Semantic search | ✅ | Consulta híbrida + reranking semántico (plan `free` activado vía azapi) |
| | Indexing | ✅ | Blob → Event Grid → Function Flex, más `ingest_local.py` |
| | Reranking | ✅ | Umbral de 1,5 sobre el reranker score |
| | RAG | ✅ | Retrieval 4,58/5 y groundedness 4,95/5 en la evaluación 4 |
| | Agentic Retrieval | ❌ | Previsto en la spec como opcional; no implementado |
| **Memory & State** | Redis / Local | ❌ | Se usa Cosmos (Redis no tiene nivel gratis) |
| | Session / Conversation State | ✅ | Cosmos `sessions` y `checkpoints` |
| | Short-term memory | ✅ | Últimos N turnos por sesión |
| | Long-term memory | ❌ | Fuera de alcance por diseño |
| **Interoperabilidad** | MCP | ✅ | `mcp-bank` propio (FastMCP, streamable HTTP, ingress interno, allowlist de Host) |
| | A2A | ❌ | Fuera de alcance |
| | Tool Calling | ✅ | Vía MCP; el plan de llamadas lo genera el LLM con salida estructurada |
| | APIs | ✅ | `products-api` y `customers-api` detrás de APIM Consumption |
| **Application & Runtime** | FastAPI | ✅ | 4 servicios |
| | Azure Container Apps | ✅ | 4 apps que escalan a cero |
| | App Service | ❌ | No se usa (sí Static Web Apps y Function Flex) |
| | Azure Functions | ✅ | Flex Consumption; trigger de Event Grid validado |
| **Evaluation & Quality** | Foundry Evaluations | ⚠️ | Evaluadores del SDK `azure-ai-evaluation`, ejecutados localmente; los resultados no se suben al proyecto de Foundry |
| | LLM-as-a-Judge | ✅ | Similarity, Groundedness y Retrieval |
| | Ground Truth | ✅ | 40 preguntas con validador contra los datos reales |
| | Human Evaluation | ❌ | No hay feedback del asesor en la UI |
| | RAG / Agent metrics | ✅ | Citation recall, tool accuracy, status accuracy y fugas |
| **Observability** | Foundry Tracing | ⚠️ | App Insights conectado al proyecto Foundry; no verifiqué la vista en el portal de Foundry |
| | Azure Monitor / Log Analytics | ✅ | Logs de sistema consultados con KQL durante el diagnóstico |
| | Application Insights | ✅ | En 3 horas: 4.242 dependencias y 328 requests de `copilot-api` |
| | OpenTelemetry | ✅ | Spans GenAI de Agent Framework más exportador a Azure Monitor con máscara de PII |
| | Custom Metrics | ⚠️ | Atributos `cost_usd_estimate` (295 spans), `authz.decision` (37) y tokens (394) verificados; el workbook está desplegado pero no lo revisé |
| **Responsible AI & Guardrails** | Azure AI Content Safety | ✅ | Prompt Shields (usuario y documentos) y groundedness QnA, en East US 2 |
| | Content Filters | ⚠️ | Los filtros por defecto de Azure OpenAI; sin filtros personalizados |
| | Guardrails | ✅ | Guard de entrada, verificador de citas y groundedness, contradicciones; seguridad 15/15 en la evaluación |
| | Tool Permissions | ✅ | Tools de solo lectura; nivel 2 solo con un permiso por campo, aplicado en `customers-api` (mutación verificada) |
| | Action Limits | ✅ | Máximo 5 tool calls por turno, rate limit por IP y tope diario de tokens (ambos se activaron en vivo) |
| **Security & Identity** | Microsoft Entra ID | ⚠️ | Entre servicios vía Managed Identity, y login de Entra para `/documentacion`; los usuarios del copiloto son personas simuladas |
| | Azure Key Vault | ✅ | Secretos y llave de personas; RBAC por secreto |
| | Managed Identity | ✅ | Una UAMI por servicio, sin llaves (Storage y Cosmos con llaves deshabilitadas) |
| **DevOps / LLMOps** | Git | ⚠️ | Repo local con historial completo; **sin remoto** (no está en GitHub) |
| | CI | ⚠️ | `deploy.yml` y `evals.yml` escritos con OIDC; nunca corrieron porque no hay repo remoto |
| | Prompt / Agent / Config versioning | ✅ | Prompts como archivos versionados, Terraform y contratos en código |
| **Data & Persistence** | Redis | ❌ | Ver Memory & State |
| | SQLite | ❌ | No se usa |
| | Azure Storage | ✅ | Blob `docs` y paquete de la Function |
| **Cognitive FinOps** | Token Usage | ✅ | Por nodo en el inspector y tope diario |
| | Latency | ✅ | p50 de 5,5 s y p95 de 28,5 s en la evaluación 4 |
| | Cost per Invocation | ✅ | `cost_usd` por traza; 40 preguntas por USD 0,05 |
| | Model / Architecture Optimization | ⚠️ | Modelo mini, escala a cero y niveles gratuitos; no hay comparación medida entre modelos |
