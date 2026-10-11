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

## Temario detallado

| Bloque | Tema | Estado | Evidencia / qué falta |
|---|---|---|---|
| **Foundry / Azure AI** | Foundry y sus componentes | ✅ | Recurso AIServices, proyecto y conexión a App Insights |
| | Model deployments y endpoints | ✅ | 2 deployments GlobalStandard por endpoint con Entra (sin llaves) |
| | Azure OpenAI y selección de modelos | ⚠️ | gpt-4.1-mini elegido sobre gpt-5-mini por latencia y costo; falta la comparación medida |
| | Prompt management y evaluación | ⚠️ | Prompts versionados en git y evaluados con 40 casos; no se usa la gestión de prompts de Foundry |
| | Knowledge / RAG con AI Search | ✅ | Híbrida + semántica, umbral de reranker |
| | Observabilidad, tracing y evaluaciones | ⚠️ | App Insights verificado; evaluaciones en Foundry en curso (`evals-foundry`) |
| | Content Safety y Responsible AI | ✅ | Prompt Shields y groundedness en vivo |
| **Agent Framework** | Creación de agentes y herramientas | ⚠️ | Executors + tools MCP; sin agentes de tool calling libre |
| | Orquestación de agentes | ✅ | Workflow con 9 nodos |
| | Workflows y grafos | ✅ | `WorkflowBuilder` con aristas condicionales |
| | Estado, memoria y contexto | ✅ | Checkpoints y sesiones en Cosmos; sin memoria de largo plazo |
| | Patrones: router / sequential | ✅ | Router + cadena secuencial |
| | Patrones: concurrent | ⚠️ | En curso: fan-out de productos y cliente (`copilot-quality`) |
| | Patrones: supervisor | ❌ | No implementado |
| | Human-in-the-loop | ✅ | Dos HITL verificados en vivo: aprobación de acceso y escalamiento |
| | Errores, retries y fallbacks | ✅ | Retry con backoff en MCP, 429 de OpenAI, fallas explícitas al usuario |
| | Frente a LangGraph / Semantic Kernel | ❌ | Falta una sección de criterios en la documentación |
| **MCP y Tool Calling** | MCP Client / Server | ✅ | `MCPStreamableHTTPTool` ↔ FastMCP propio |
| | Tools y resources | ⚠️ | 5 tools; ningún MCP *resource* expuesto |
| | Exposición de APIs como herramientas | ✅ | `mcp-bank` envuelve products-api y customers-api |
| | MCP Gateway | ❌ | APIM Consumption no aloja MCP; APIM delante de las APIs (decisión de costo) |
| | Autenticación / autorización | ✅ | JWT reenviado, allowlist de Host, subscription key, X-Backend-Secret |
| | Agent → MCP → API | ✅ | Verificado en vivo hasta el 403 de nivel 2 |
| | MCP vs tool calling directo | ⚠️ | Decisión tomada, pero no documentada como criterio |
| **Arquitecturas agentic** | Single vs multi-agent | ⚠️ | Multi-rol en un grafo; falta el criterio escrito |
| | Agentes basados en grafos | ✅ | |
| | Router / Supervisor / Orchestrator | ⚠️ | Router y orquestador sí; supervisor no |
| | Agent-as-a-Judge / LLM-as-a-Judge | ✅ | Jueces de la evaluación y verificador de groundedness |
| | Guardrails | ✅ | Seguridad 15/15 |
| | Planning y reasoning | ⚠️ | Planes estructurados de tool calls; sin modelo de razonamiento |
| | Memoria corto / largo plazo | ⚠️ | Corto sí, largo no |
| | RAG agentic | ⚠️ | En curso: agentic retrieval de AI Search (`copilot-quality`) |
| | Evaluación y trazabilidad E2E | ✅ | Evaluación + trazas por nodo + auditoría |
| **Stack Azure Cloud** | Container Apps / Functions | ✅ | |
| | AKS / App Service | ❌ | Solo documentado en "Producción objetivo" |
| | API Management | ✅ | Consumption con policies |
| | Entra ID y Managed Identity | ⚠️ / ✅ | MI sí; Entra para usuarios solo en `/documentacion` |
| | Key Vault | ✅ | |
| | Azure AI Search | ✅ | |
| | Storage / Cosmos DB | ✅ | |
| | Event Grid | ✅ | Blob → Function verificado |
| | Service Bus | ❌ | No se usa |
| | App Insights / Monitor / OpenTelemetry | ✅ | |
| | VNet, Private Endpoint, Private DNS | ❌ | Costo fijo; documentado como producción objetivo |
| | CI/CD con GitHub Actions | ⚠️ | Workflows escritos; falta el repo remoto |
| | IaC con Terraform | ✅ | Unos 104 recursos, con tests de invariantes |
| **Seguridad y gobierno** | RBAC y mínimo privilegio | ✅ | Roles por secreto y por contenedor |
| | Managed Identities | ✅ | Una por servicio |
| | Gestión de secretos | ✅ | Key Vault; state fuera del repo |
| | Private networking | ❌ | |
| | PII y datos sensibles | ✅ | Niveles 0–3, máscara de PII en spans, historial sin nivel 2, 0 fugas |
| | Prompt injection y tool poisoning | ✅ | Prompt Shields en documentos (e37 en vivo) y salidas de tools validadas |
| | Autorización de tools | ✅ | Permisos por campo en customers-api |
| | Auditoría de acciones de agentes | ✅ | Contenedor `audit` (tests); no revisado en vivo |
| | Human approval para acciones críticas | ✅ | Escalamiento y acceso a nivel 2 |
| | Evaluaciones, guardrails y políticas | ✅ | |
