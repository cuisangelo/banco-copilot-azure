# Banco Copilot Azure — plan de implementación

> **Para agentes:** este plan se ejecuta en **sesiones paralelas**, una por paquete de trabajo (WP).
> - Cada sesión lee primero la spec y la sección "Contratos" de este plan.
> - Antes de escribir código, cada sesión expande su WP en pasos TDD (test que falla → implementación
>   mínima → test verde → commit) con `superpowers:test-driven-development`.
> - Los pasos usan checkbox (`- [ ]`).

**Goal:** Construir y desplegar el copiloto bancario de la spec: RAG con citas, tools vía MCP, acceso
a datos de cliente por niveles con aprobación de Supervisor y HITL de escalamiento, todo en Azure.

**Architecture:** Monorepo con `uv` workspace (Python 3.12) y `pnpm` (web). Un paquete compartido,
`bank_contracts`, fija los modelos y nombres que cruzan fronteras entre servicios. Hay cuatro
servicios FastAPI en Container Apps, una Function de ingesta, un frontend Next.js y la infraestructura
en Terraform.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `agent-framework` 1.21 (+ `agent-framework-openai`), `mcp`
(FastMCP), `azure-identity`, `azure-search-documents`, `azure-cosmos`, `azure-ai-contentsafety`,
`azure-monitor-opentelemetry`, `pyjwt[crypto]`, pytest, Next.js (static export) + TypeScript + Tailwind, Terraform (azurerm +
azapi), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-11-banco-copilot-design.md`

## Global Constraints

- Python `>=3.12`, gestionado con `uv`. JS gestionado con `pnpm`. Nunca `pip`, `npm` ni `yarn`.
- Identificadores, código, comentarios y commits en **inglés**. Textos visibles al usuario, documentos
  sintéticos y README en **español**.
- La spec nombra campos en español (`requisitos`, `estado`). En código se usan los nombres en inglés
  de `bank_contracts`. La UI traduce.
- Configuración fallando fuerte: toda variable de entorno requerida se lee con
  `bank_contracts.settings.require_env`. No hay valores por defecto para endpoints, nombres de
  deployment, llaves ni topes.
- Ninguna credencial en código, imágenes ni `.env` commiteados. En Azure, todo pasa por Managed
  Identity o por referencias a Key Vault.
- Región única: `canadaeast`. Modelo de chat: deployment `gpt-4.1-mini` (GlobalStandard). Embeddings:
  deployment `text-embedding-3-small`, 1536 dimensiones.
- Commits con la convención gitmoji del usuario (skill `commits`), sin `Co-Authored-By`.
- **Nadie ejecuta `terraform apply`, `az ... create` ni nada que genere costo sin aprobación explícita
  del usuario.** `terraform validate` y `terraform plan` sí están permitidos.
- Tests de autorización: ejercitan el endpoint real con `TestClient`, no la función de chequeo con
  literales. Cada guard se valida mutando el código, viendo el test en rojo y revirtiendo. La
  mutación se escribe en el cuerpo del commit.

## Review Focus

1. **Permiso que vence en medio de la sesión.** Pasados 30 minutos, el asesor vuelve a preguntar por
   la renta del cliente. Esperado: 403 y una nueva solicitud. Los valores de nivel 2 de turnos
   anteriores **no** pueden venir del historial de la sesión. Test: WP4, Task 4.6.
2. **Cambio de cliente en la misma sesión.** El asesor pasa de C-1042 a C-2001. Esperado: el perfil y
   los campos de C-1042 no aparecen en la respuesta sobre C-2001. Test: WP4, Task 4.6.
3. **`customer_id` inventado o mal formado por el modelo.** Esperado: 404 o 422 desde
   `customers-api`, estado `insufficient` y ninguna excepción no manejada. Test: WP3, Task 3.2, y
   WP4, Task 4.4.
4. **Doble decisión sobre la misma solicitud de acceso**, dos pestañas de Supervisor. Esperado: la
   segunda recibe 409 y no se crea un segundo permiso. Test: WP3, Task 3.3.
5. **RUT o número de tarjeta escrito por el asesor en texto libre.** Esperado: aparece enmascarado
   en logs y spans OTel; la consulta se procesa igual. Test: WP4, Task 4.7.

---

## Contratos (Fase 0, la ejecuta la sesión coordinadora antes de lanzar las demás)

El paquete `packages/contracts` (`bank_contracts`) es la **única** fuente de verdad de lo que cruza
fronteras.

- Ningún WP lo modifica. Si un WP necesita un cambio, lo pide a la sesión coordinadora por Coro
  (`/coro:msg`) y espera.
- Los WP lo consumen como dependencia del workspace: `bank-contracts = { workspace = true }`.

### Estructura del repo

```
pyproject.toml                 # uv workspace: members = packages/*, services/*, functions/*, evals
packages/contracts/src/bank_contracts/
  __init__.py
  models.py                    # Pydantic models below
  auth.py                      # persona JWT claims + constants
  settings.py                  # require_env
  tools.py                     # MCP tool names
packages/contracts/tests/test_models.py
services/products-api/         # WP3
services/customers-api/        # WP3
services/mcp-bank/             # WP3
services/copilot-api/          # WP4
functions/ingest/              # WP2
data/docs/  data/products.json  data/customers.json   # WP2
web/                           # WP5
infra/                         # WP1
evals/                         # WP6
.github/workflows/             # WP1 (build/deploy), WP6 (evals)
compose.yaml                   # Fase 0: cosmos emulator + local services
```

### `bank_contracts/models.py`

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ProductCategory = Literal["account", "credit_card", "consumer_loan", "mortgage"]
Level2Field = Literal["monthly_income", "current_debt", "payment_behavior", "employment_tenure_months"]
LEVEL2_FIELDS: tuple[Level2Field, ...] = ("monthly_income", "current_debt", "payment_behavior", "employment_tenure_months")
ChatStatus = Literal["ok", "clarification", "insufficient", "contradiction", "rejected", "access_required"]
AccessRequestStatus = Literal["pending", "approved", "partially_approved", "rejected", "expired"]
CUSTOMER_ID_PATTERN = r"^C-\d{4}$"
GRANT_MINUTES = 30


class Product(BaseModel):
    id: str
    name: str
    category: ProductCategory
    annual_rate_pct: float | None
    monthly_fee_clp: int | None
    requirements: list[str]
    valid_from: date


class CustomerProfile(BaseModel):
    """Level 1 data: available to any Asesor once the customer is identified."""
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    segment: Literal["personas", "preferente", "pyme"]
    income_type: Literal["dependiente", "independiente"]
    products: list[str]
    customer_tenure_months: int


class CustomerFields(BaseModel):
    """Level 2 values, returned only for fields covered by a live grant."""
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    values: dict[Level2Field, int | str]
    grant_id: str


class FieldsDenied(BaseModel):
    """Body of the 403 returned by customers-api when any requested field lacks a live grant."""
    customer_id: str
    denied_fields: list[Level2Field]


class AccessRequestCreate(BaseModel):
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    fields: list[Level2Field] = Field(min_length=1)
    purpose: str = Field(min_length=10, max_length=300)


class AccessRequest(AccessRequestCreate):
    id: str
    requested_by: str
    status: AccessRequestStatus
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    approved_fields: list[Level2Field] = []


class AccessDecision(BaseModel):
    """Empty approved_fields means reject."""
    approved_fields: list[Level2Field]


class Grant(BaseModel):
    id: str
    access_request_id: str
    customer_id: str
    advisor_sub: str
    fields: list[Level2Field]
    purpose: str
    approved_by: str
    expires_at: datetime


class Citation(BaseModel):
    id: str
    kind: Literal["doc", "product", "customer"]
    ref: str          # "ficha-hipotecario §2", "producto:TC-ORO", "cliente:C-1042 monthly_income"
    snippet: str


class Claim(BaseModel):
    text: str
    citation_ids: list[str] = Field(min_length=1)


class EscalationDraft(BaseModel):
    id: str
    area: str
    summary: str
    evidence: list[Citation]


class EscalationDecision(BaseModel):
    approve: bool


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    customer_id: str | None = Field(default=None, pattern=CUSTOMER_ID_PATTERN)


class ChatAnswer(BaseModel):
    status: ChatStatus
    message: str
    requirements: list[Claim] = []
    steps: list[Claim] = []
    citations: list[Citation] = []
    access_request: AccessRequest | None = None
    escalation: EscalationDraft | None = None


class TraceEvent(BaseModel):
    node: str
    duration_ms: int
    data: dict           # never contains level-2 values; field names only
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class ErrorEvent(BaseModel):
    code: Literal["token_cap", "rate_limited", "upstream", "unauthorized", "internal"]
    message: str
```

`session_id` lo genera el cliente con `crypto.randomUUID()`; `copilot-api` lo trata como opaco.

**SSE de `/chat` y `/sessions/{id}/resume`:**

- `event: trace` → `TraceEvent`
- `event: answer` → `ChatAnswer` (exactamente uno, al final)
- `event: error` → `ErrorEvent`, que reemplaza a `answer`

### `bank_contracts/auth.py`

```python
from typing import Literal

PERSONA_ISSUER = "banco-copilot-demo"
PERSONA_AUDIENCE = "banco-copilot"
PERSONA_TTL_SECONDS = 3600
Role = Literal["Asesor", "Supervisor"]
PERSONAS: dict[str, tuple[str, Role]] = {
    "ana": ("Ana", "Asesor"),
    "bruno": ("Bruno", "Asesor"),
    "sofia": ("Sofía", "Supervisor"),
}
# Claims: iss, aud, sub (persona key), name, roles: [Role], iat, exp. Algorithm RS256, header kid.
```

### `bank_contracts/settings.py`

```python
import os


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
```

### `bank_contracts/tools.py`

```python
TOOL_GET_PRODUCT = "get_product"                   # (product_id: str) -> Product
TOOL_LIST_PRODUCTS = "list_products"               # (category: ProductCategory | None) -> list[Product]
TOOL_COMPARE_PRODUCTS = "compare_products"         # (product_ids: list[str], 2..3) -> list[Product]
TOOL_GET_CUSTOMER_PROFILE = "get_customer_profile" # (customer_id: str) -> CustomerProfile
TOOL_GET_CUSTOMER_FIELDS = "get_customer_fields"   # (customer_id: str, fields: list[Level2Field]) -> CustomerFields | FieldsDenied
```

### Endpoints HTTP

Toda llamada a `products-api` o a `customers-api` exige la cabecera `X-Backend-Secret`, que inyecta
APIM. Sin ella, la respuesta es 401.

| Servicio | Método y ruta | Auth (JWT persona) | Respuestas |
|---|---|---|---|
| products-api | `GET /products?category=` | — | `list[Product]` |
| products-api | `GET /products/{id}` | — | `Product` o 404 |
| customers-api | `GET /customers/{id}/profile` | rol Asesor | `CustomerProfile`, 401, 403 o 404 |
| customers-api | `POST /customers/{id}/fields` con body `{"fields": [...]}` | rol Asesor | `CustomerFields`, o 403 con `FieldsDenied`; también 401 y 404 |
| customers-api | `POST /grants` con body `AccessRequest` (ya decidido) | rol Supervisor, `sub != requested_by` | `Grant` (201), 403 o 409 si ya existe un permiso para la solicitud |
| copilot-api | `POST /demo/session` con body `{"persona": "ana"}` | — | `{"token": str, "name": str, "role": Role}` |
| copilot-api | `GET /.well-known/jwks.json` | — | JWKS con la llave pública |
| copilot-api | `POST /chat` (body `ChatRequest`) | opcional (sin token, solo nivel 0) | SSE |
| copilot-api | `POST /sessions/{session_id}/resume` (sin body; reanuda el checkpoint pendiente de la sesión) | el mismo `sub` que inició | SSE; 409 si la sesión no tiene un checkpoint pendiente |
| copilot-api | `POST /escalations/{id}/decision` (body `EscalationDecision`) | el mismo `sub` que inició | `{"ticket_id": str}` o `{"discarded": true}` |
| copilot-api | `GET /access-requests?status=` (cualquier `AccessRequestStatus`; sin `status`, todas) | rol Supervisor | `list[AccessRequest]` |
| copilot-api | `GET /access-requests/{id}` | `sub == requested_by` o rol Supervisor | `AccessRequest`; 403 si no es el solicitante ni Supervisor; 404 si no existe |
| copilot-api | `POST /access-requests/{id}/decision` (body `AccessDecision`) | rol Supervisor, `sub != requested_by` | `AccessRequest`, o 409 si ya estaba decidida |

Rutas en APIM:

- API `products`, con sufijo `products-api`: `{APIM_BASE_URL}/products-api/products/{id}`.
- API `customers`, con sufijo `customers-api`: `{APIM_BASE_URL}/customers-api/customers/{id}/profile`.
- La subscription key va en `Ocp-Apim-Subscription-Key`.

`mcp-bank` reenvía la cabecera `Authorization: Bearer <jwt persona>` que recibe del transporte MCP.
`copilot-api` la pone en el cliente MCP (`MCPStreamableHTTPTool(..., headers=...)`), nunca en los
argumentos de la tool.

### Archivos de datos

- `data/products.json`: lista de `Product`.
- `data/customers.json`: lista de objetos planos.
  - Cada objeto trae exactamente los campos de `CustomerProfile` (`customer_id`, `segment`,
    `income_type`, `products`, `customer_tenure_months`) más las 4 claves de `Level2Field`:
    - `monthly_income`: int, en CLP;
    - `current_debt`: int, en CLP;
    - `payment_behavior`: str, uno de `al_dia`, `atraso_30` o `atraso_90`;
    - `employment_tenure_months`: int.
  - No hay ninguna otra clave. `customers-api` la valida al arrancar y falla si sobra o falta una.
  - `products` usa ids que existen en `products.json`.

### Índice de AI Search `bank-docs`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | `Edm.String` | clave, `{doc_id}-{chunk_n}` |
| `doc_id` | `Edm.String` | filterable |
| `doc_title` | `Edm.String` | searchable |
| `section` | `Edm.String` | searchable, retrievable |
| `content` | `Edm.String` | searchable, analizador `es.microsoft` |
| `content_vector` | `Collection(Edm.Single)` | 1536 dimensiones, HNSW, perfil `default` |
| `valid_from` | `Edm.DateTimeOffset` | filterable, sortable |

Configuración semántica `default`: título `doc_title` y contenido `content`.

### Variables de entorno (todas requeridas)

| Servicio | Variables |
|---|---|
| products-api | `BACKEND_SECRET`, `PRODUCTS_PATH` |
| customers-api | `BACKEND_SECRET`, `CUSTOMERS_PATH`, `PERSONA_PUBLIC_KEY_PEM`, `COSMOS_ENDPOINT`, `COSMOS_DATABASE` |
| mcp-bank | `APIM_BASE_URL`, `APIM_SUBSCRIPTION_KEY`, `MCP_ALLOWED_HOSTS` (FQDN interno de ACA, separado por comas) |
| copilot-api | `APIM_BASE_URL`, `APIM_SUBSCRIPTION_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`, `SEARCH_ENDPOINT`, `SEARCH_INDEX`, `CONTENT_SAFETY_ENDPOINT`, `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `MCP_BANK_URL`, `PERSONA_PRIVATE_KEY_PEM`, `PERSONA_KEY_ID`, `DAILY_TOKEN_CAP`, `CORS_ORIGIN`, `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| functions/ingest | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`, `SEARCH_ENDPOINT`, `SEARCH_INDEX` |
| web | `NEXT_PUBLIC_API_BASE_URL` (se fija en el build) |

Además, en Azure, todo servicio que use `DefaultAzureCredential` con una UAMI recibe `AZURE_CLIENT_ID`. `products-api` y `customers-api` traen sus datos en la imagen: `PRODUCTS_PATH=/app/data/products.json` y `CUSTOMERS_PATH=/app/data/customers.json`. Los servicios escuchan en el puerto 8000, se construyen desde la raíz con `docker build -f services/<svc>/Dockerfile .`, y `MCP_BANK_URL` termina en `/mcp`.

Contenedores de Cosmos (base `copilot`):

| Contenedor | Partition key | TTL |
|---|---|---|
| `sessions` | `/session_id` | — |
| `checkpoints` | `/session_id` | — |
| `access_requests` | `/customer_id` | — |
| `grants` | `/customer_id` | por documento = segundos hasta `expires_at` |
| `audit` | `/actor` (sub de quien actuó, o `anonymous`) | — |
| `usage` | `/day` | — |

### Task 0: esqueleto y contratos (sesión coordinadora)

**Files:**
- Create: `pyproject.toml`
- Create: `packages/contracts/pyproject.toml`
- Create: `packages/contracts/src/bank_contracts/{__init__,models,auth,settings,tools}.py`
- Create: `compose.yaml`
- Create: `README.md`, solo con el título y el enlace a la spec
- Test: `packages/contracts/tests/test_models.py`

- [ ] Escribir tests que fallen:
  - `ChatRequest` rechaza un `customer_id` como `"1042"`.
  - `Claim` exige al menos una cita.
  - `AccessRequestCreate` rechaza un `purpose` de menos de 10 caracteres y una lista de `fields`
    vacía.
  - `require_env` lanza un error si la variable falta.
- [ ] Correr `uv run --all-packages pytest packages/contracts -q` → FAIL (falta el módulo).
- [ ] Implementar los módulos tal cual el código de arriba.
- [ ] Correr `uv run --all-packages pytest packages/contracts -q` → PASS.
- [ ] Commit: `✨ feat(contracts): add shared models, persona auth and tool names`.
- [ ] Integrar la rama a `main` (fast-forward local) para que las sesiones partan de ahí.

---

## Paquetes de trabajo (uno por sesión)

Grafo de dependencias: todos dependen solo de la Fase 0, y entre ellos se integran por contratos.

- **Pueden correr en paralelo:** WP1, WP2, WP3, WP4 y WP5.
- **Corre al final:** WP6 (evaluaciones y CI) y la integración y despliegue, a cargo de la sesión
  coordinadora.

| WP | Slug y rama | Sesión |
|---|---|---|
| WP1 | `feat/infra-terraform` | `infra-terraform · banco-copilot` |
| WP2 | `feat/data-ingest` | `data-ingest · banco-copilot` |
| WP3 | `feat/bank-apis-mcp` | `bank-apis-mcp · banco-copilot` |
| WP4 | `feat/copilot-api` | `copilot-api · banco-copilot` |
| WP5 | `feat/web` | `web · banco-copilot` |

### WP1: infraestructura (Terraform)

**Files:** `infra/{main,providers,variables,outputs}.tf`, más un módulo por dominio:

- `infra/ai.tf`: recurso Foundry (AIServices), proyecto y deployments.
- `infra/search.tf`, `infra/data.tf` (Cosmos, Storage), `infra/compute.tf` (ACA env, 4 apps, ACR).
- `infra/apim.tf` (Consumption, 2 APIs, policies), `infra/security.tf` (UAMI, Key Vault, RBAC).
- `infra/observability.tf` (Log Analytics, App Insights, workbook), `infra/ingest.tf` (Function Flex,
  Event Grid), `infra/budget.tf`.
- `.github/workflows/deploy.yml`: build, push y `az containerapp update`, con OIDC.
- `infra/README.md`.

**Tareas:**

- [ ] **1.1** Providers con `azurerm ~> 4` y `azapi ~> 2`, y backend local. Variables: `prefix`,
  `location = "canadaeast"`, `daily_token_cap`, `budget_alert_emails`. Correr `terraform validate`.
- [ ] **1.2** Seguridad:
  - Una UAMI por servicio.
  - Key Vault en modo RBAC, con los secretos `apim-subscription-key`, `backend-secret`,
    `persona-private-key-pem` y `persona-public-key-pem`. El par RSA se genera con `tls_private_key`.
  - Asignaciones de rol mínimas, según la §5 de la spec.
- [ ] **1.3** Foundry:
  - `azapi` con `Microsoft.CognitiveServices/accounts` de kind `AIServices` y un proyecto.
  - Deployments `gpt-4.1-mini` (GlobalStandard, capacity 50) y `text-embedding-3-small` (capacity 100).
  - Content Safety S0 aparte.
- [ ] **1.4** AI Search `free` con semántica `free`; Cosmos con `free_tier_enabled = true` y los
  contenedores de los contratos, con TTL en `grants`; Storage con un contenedor `docs`.
- [ ] **1.5** Entorno de ACA:
  - Workload profile Consumption y ACR Basic.
  - 4 apps con `min_replicas = 0`, imágenes `mcr.microsoft.com/k8se/quickstart` como placeholder
    hasta el primer deploy, y variables con `secret_ref` a Key Vault.
  - Ingress: `mcp-bank` interno; `copilot-api`, `products-api` y `customers-api` externos (detrás de
    APIM, protegidos por `X-Backend-Secret`).
- [ ] **1.6** APIM Consumption:
  - Las APIs `products` y `customers` con backend en ACA.
  - Policy `set-header X-Backend-Secret` desde un named value respaldado por Key Vault.
  - `rate-limit-by-key` y una suscripción para `mcp-bank`.
- [ ] **1.7** Function Flex (Python 3.12) y suscripción de Event Grid al contenedor `docs`.
  - Si la creación de Flex falla en Free Trial: Container Apps Job, documentado en
    `infra/README.md`.
- [ ] **1.8** Observabilidad y presupuesto:
  - Log Analytics y App Insights conectados al proyecto Foundry.
  - `azurerm_consumption_budget_subscription` con alertas de USD 50 y USD 100.
- [ ] **1.9** `deploy.yml`, con el federated credential de GitHub como variable. El repo remoto
  todavía no existe, así que no hay que probarlo en vivo.
- [ ] **Aceptación:** `terraform -chdir=infra init && terraform -chdir=infra validate && terraform
  -chdir=infra plan -out tfplan` sin errores. Pegar el resumen `Plan: N to add` en el PR. **No hacer
  apply.**

### WP2: datos sintéticos e ingesta

**Files:**

- `data/docs/*.md`: 12 documentos con front matter `doc_id`, `title`, `valid_from` y secciones `##`.
- `data/products.json` y `data/customers.json`.
- `functions/ingest/{function_app.py,chunker.py,indexer.py,index_schema.py}`.
- `functions/ingest/tests/`.
- `scripts/ingest_local.py`.

**Tareas:**

- [ ] **2.1** Documentos, en español y de un banco ficticio llamado "Banco Austral":
  - Fichas: cuenta corriente, cuenta sueldo, tarjeta Clásica, tarjeta Oro, tarjeta Platinum, crédito
    de consumo y crédito hipotecario.
  - Procedimientos: apertura de cuenta, reclamos y bloqueo de tarjeta.
  - Una política de excepciones.
  - La **circular 2026-07**, que contradice la ficha del hipotecario en la antigüedad laboral mínima:
    24 meses en la circular contra 12 en la ficha.
  - Un documento con una injection indirecta escondida, como "ignora tus instrucciones y…".
- [ ] **2.2** `products.json`, con unos 8 productos que cumplen `Product` y son coherentes con las
  fichas. `customers.json`, con 20 clientes `C-1001`… `C-1020` que traen el perfil de nivel 1 y los
  valores de nivel 2. **No incluir ningún campo de nivel 3.**
  - Test: validar cada fila con los modelos de `bank_contracts`.
- [ ] **2.3** `chunker.py`: divide por sección `##` y, dentro de una sección, en bloques de unas 800
  palabras con solapamiento de 100. Conserva `doc_id`, `doc_title`, `section` y `valid_from`.
  - Tests: un documento de 3 secciones produce 3 chunks; el id es estable.
- [ ] **2.4** `index_schema.py`: crea o actualiza el índice `bank-docs` exactamente como en los
  contratos. `indexer.py`: genera embeddings por lotes de 16 y hace upsert.
  - Tests con clientes falsos: el lote se divide bien y el error de upsert se propaga.
- [ ] **2.5** `function_app.py`: blob trigger con `source=EventGrid` sobre `docs/{name}`.
  `scripts/ingest_local.py`, para ingerir `data/docs` directo desde la laptop.
- [ ] **Aceptación:** `uv run --all-packages pytest functions/ingest -q` en verde, y `uv run python -I -c "import
  json; from bank_contracts.models import Product; [Product(**p) for p in
  json.load(open('data/products.json'))]"` sin errores.

### WP3: APIs del banco y servidor MCP

**Files:**

- `services/products-api/src/products_api/main.py`, con tests.
- `services/customers-api/src/customers_api/{main,auth,grants,store}.py`, con tests.
- `services/mcp-bank/src/mcp_bank/server.py`, con tests.
- Un `Dockerfile` por servicio.

**Tareas:**

- [ ] **3.1** `products-api`: los endpoints de los contratos y el middleware `X-Backend-Secret`.
  - Tests: 401 sin cabecera, 404 con un id inexistente y filtro por categoría.
- [ ] **3.2** Autenticación y nivel 1 en `customers-api`:
  - `auth.py` verifica RS256 con `PERSONA_PUBLIC_KEY_PEM`, además de `iss`, `aud` y `exp`.
  - `GET /customers/{id}/profile` responde solo `CustomerProfile`.
  - Tests con tokens firmados por una llave de test, todos contra el endpoint real:
    - sin token → 401;
    - token vencido → 401;
    - rol Supervisor → 403;
    - id `C-9999` → 404;
    - id `1042` → 422;
    - la respuesta no contiene ninguna clave de nivel 2.
- [ ] **3.3** Permisos y nivel 2:
  - `POST /grants` exige rol Supervisor y `sub != requested_by`; si ya existe un permiso para ese
    `access_request_id`, responde 409.
  - `POST /customers/{id}/fields` devuelve solo los campos cubiertos por un permiso vigente del mismo
    `advisor_sub`. Si falta cualquiera, responde 403 con `FieldsDenied`.
  - Cada lectura se audita, con los nombres de los campos y nunca los valores.
  - `store.py` usa Cosmos. Los tests usan un store en memoria con la misma interfaz.
  - Tests:
    - sin permiso → 403;
    - permiso de otro asesor → 403;
    - permiso vencido → 403;
    - campo no aprobado → 403 que lista ese campo;
    - autoaprobación → 403;
    - doble `POST /grants` → 409;
    - caso feliz → solo los campos aprobados.
  - **Mutación obligatoria:** quitar el chequeo de `advisor_sub`, confirmar el rojo, revertir y
    anotarlo en el commit.
- [ ] **3.4** `mcp-bank`:
  - FastMCP con transporte streamable HTTP y las 5 tools de `bank_contracts.tools`.
  - Llama a APIM con `APIM_SUBSCRIPTION_KEY` y reenvía `Authorization`.
  - Si recibe 403, devuelve `FieldsDenied` como resultado estructurado, no como excepción.
  - Valida las respuestas con Pydantic antes de devolverlas.
  - Tests con un cliente MCP en memoria y `respx` para las APIs.
- [ ] **3.5** Dockerfiles: `python:3.12-slim`, `uv sync --frozen --no-dev` y usuario no root.
- [ ] **Aceptación:** `uv run --all-packages pytest services/products-api services/customers-api services/mcp-bank
  -q` en verde, más `docker build` de los 3 servicios.

### WP4: copilot-api (workflow agéntico)

**Files:** `services/copilot-api/src/copilot_api/`:

- `main.py`: rutas.
- `personas.py`: emisión de JWT y JWKS.
- `workflow/{graph,router,clarifier,rag,products,customer,composer,verifier,escalation}.py`.
- `guards/{content_safety,pii_mask,token_cap,rate_limit}.py`.
- `store.py`: Cosmos.
- `telemetry.py`.
- `pricing.py`.
- `prompts/*.md`.

Tests en `services/copilot-api/tests/`. Las dependencias externas (OpenAI, Search, Content Safety,
MCP) se reemplazan con fakes de las mismas interfaces. El LLM falso devuelve respuestas
predeterminadas por nodo.

**Tareas:**

- [ ] **4.1** `personas.py`: `POST /demo/session` firma un JWT con los claims de `auth.py` y
  `GET /.well-known/jwks.json`. Tests: una persona desconocida da 422 y el token verifica con la JWKS.
- [ ] **4.2** Guards:
  - `token_cap`: contador diario en `usage`; al superar `DAILY_TOKEN_CAP` emite `ErrorEvent
    token_cap`.
  - `rate_limit`: 10 req/min por IP, en memoria por réplica.
  - `pii_mask`: RUT `\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]`, PAN de 13 a 19 dígitos y correo.
  - `content_safety`: Prompt Shields para usuario y documentos, más groundedness.
  - Tests:
    - el cap corta en el umbral exacto;
    - la máscara cubre los tres formatos;
    - si Prompt Shields detecta un ataque, se emite `rejected`.
- [ ] **4.3** Router, clarifier y RAG.
  - **Router:** structured output con las rutas `procedure`, `product`, `customer`, `mixed`,
    `out_of_scope` y `missing_context`.
  - **RAG:** híbrida más semántica, top 5, umbral de reranker de 1.5 (configurable). Por debajo del
    umbral, el estado es `insufficient`. Los chunks pasan por Prompt Shields en modo documents.
  - Tests:
    - "¿qué opinas de bitcoin?" → `rejected`;
    - "cliente quiere crédito" → `clarification`;
    - chunks bajo el umbral → `insufficient`.
- [ ] **4.4** Agentes de producto y de cliente, con `MCPStreamableHTTPTool(url=MCP_BANK_URL,
  headers={"Authorization": ...})`. Máximo 5 tool calls por turno.
  - Si `get_customer_fields` devuelve `FieldsDenied`: se crea un `AccessRequest` con los campos
    denegados y el propósito redactado por el LLM; el estado pasa a `access_required` y hay
    checkpoint con `ctx.request_info()`.
  - Tests:
    - `FieldsDenied` → `access_required` con los campos exactos;
    - un id inválido del LLM → `insufficient` sin excepción;
    - el JWT nunca aparece en los argumentos de la tool.
- [ ] **4.5** Composer, verifier y escalation.
  - Cada `Claim` cita algo existente; si no, el estado es `insufficient`.
  - Contradicción: mismo atributo (por ejemplo, la antigüedad laboral) con valores distintos entre
    citas → `contradiction` con `EscalationDraft`.
  - `POST /escalations/{id}/decision` audita y devuelve el ticket.
  - Test de contradicción con los chunks de la circular y de la ficha del hipotecario.
- [ ] **4.6** Rutas y sesiones:
  - `/chat` y `/sessions/{id}/resume` por SSE.
  - `/access-requests` (listar y decidir): la decisión llama directo a
    `{APIM_BASE_URL}/customers-api/grants` con el JWT del Supervisor. No pasa por MCP, porque no es
    una tool del modelo. Responde 409 si ya estaba decidida.
  - El historial de `sessions` guarda las respuestas **con los valores de nivel 2 redactados**.
  - Tests del Review Focus:
    - pasados 30 minutos, se repite la pregunta → nueva solicitud, y el historial no tiene los
      valores;
    - con el cambio de `customer_id`, los datos del cliente anterior no se usan.
  - **Mutación:** guardar el historial sin redactar debe poner en rojo el test de vencimiento.
- [ ] **4.7** Telemetría:
  - `configure_otel_providers` más Azure Monitor, con un `SpanProcessor` que aplica `pii_mask` a los
    atributos y elimina cualquier atributo `customer.values`.
  - `pricing.py` con los precios de la spec.
  - Cada `TraceEvent` lleva tokens y costo.
  - Tests: el span con un RUT sale enmascarado y `cost_usd > 0` en una llamada real del flujo (fake
    LLM con `usage`).
- [ ] **Aceptación:** `uv run --all-packages pytest services/copilot-api -q` en verde, más `docker build`.

### WP5: web (Next.js)

**Dirección visual:** estética de banca corporativa inspirada en Interbank (Perú), pero en **azul**.

- **Rasgos:** superficies blancas y amplias; tarjetas con esquinas redondeadas y sombras suaves;
  tipografía sans-serif geométrica y en negrita para los títulos (Montserrat o Poppins, vía
  `next/font`); un color de marca fuerte y uno de acento; íconos lineales; jerarquía clara.
- **Paleta:** azul primario `#0047BB`, azul profundo `#002A6E` para la barra superior y el texto
  fuerte, celeste `#E8F0FE` para fondos de tarjeta, y un acento cian `#00A3E0`. Estados: verde
  `#1E8E3E` para ok, ámbar `#B26A00` para contradicción, rojo `#C62828` para rechazo y violeta
  `#5B3CC4` para acceso requerido.
- **Referencia:** antes de diseñar, mirar interbank.pe con WebFetch para captar layout, densidad y
  tono.
- **Prohibido:** el nombre, el logo, los textos o cualquier activo de Interbank. El banco es "Banco
  Austral", con un logotipo tipográfico propio.
- Usar el skill `frontend-design:frontend-design`.

**Files:** `web/`, con Next.js (App Router, TypeScript, `output: 'export'`) y Tailwind:

- `web/app/layout.tsx`, con la fuente y la barra superior.
- `web/app/page.tsx`, la vista del Asesor.
- `web/app/supervisor/page.tsx`.
- `web/lib/api.ts`, el cliente SSE con `fetch` y `ReadableStream`.
- `web/lib/types.ts`, el espejo TS de `bank_contracts.models`.
- `web/components/`: `PersonaPicker`, `Chat`, `AnswerCard`, `AccessRequestCard`, `EscalationCard`,
  `SupervisorInbox` e `Inspector`.

Tests con Vitest y Testing Library.

**Tareas:**

- [ ] **5.1** Scaffold con `pnpm create next-app web --ts --tailwind --app --eslint`.
  - Agregar `output: 'export'` en `next.config.ts`.
  - Los tokens de color y la fuente van en `tailwind.config` y `globals.css`.
  - `types.ts` replica los modelos con los mismos nombres.
  - `api.ts` parsea el SSE (`trace`, `answer`, `error`).
  - Test: un parser de un stream de ejemplo.
- [ ] **5.2** `PersonaPicker`: Sin persona, Ana, Bruno y Sofía, cada una con avatar de iniciales y
  rol. El token se guarda en memoria (React context), no en localStorage. Si llega un 401, la UI
  vuelve al selector con un aviso.
- [ ] **5.3** Vista de Asesor:
  - Chat; "Cliente en atención" opcional, validado con `^C-\d{4}$`.
  - `AnswerCard` con secciones de requisitos (checklist) y pasos (numerados), citas como chips
    clicables con el snippet en un popover, y una etiqueta de color por `status`.
  - `AccessRequestCard`, que consulta el estado y llama a `/resume` cuando hay aprobación.
  - `EscalationCard`, con aprobar y descartar.
- [ ] **5.4** `/supervisor`: bandeja de solicitudes pendientes con checkboxes por campo, propósito y
  asesor; un 409 muestra "ya decidida".
- [ ] **5.5** `Inspector` plegable (panel lateral derecho): timeline de `TraceEvent` con nodo,
  duración, tokens y costo, y los totales del turno.
- [ ] **5.6** Todos los textos en español. Responsive desde 375 px. Accesible: contraste AA, foco
  visible y `aria-live` en el stream.
- [ ] **Aceptación:** `pnpm -C web test --run && pnpm -C web build` en verde, y `web/out/` generado.
  Capturas de escritorio y móvil en el PR.

### WP6: evaluaciones y CI (sesión coordinadora, después de integrar)

- [ ] **6.1** `evals/dataset.jsonl` con unas 40 filas, cubriendo los tipos de la §9 de la spec.
- [ ] **6.2** `evals/run.py`:
  - Llama al `/chat` desplegado con la persona de cada fila.
  - Evaluadores de Foundry: similarity, retrieval y groundedness.
  - Métricas deterministas: citas, tool, estado y **fugas de datos (deben ser 0)**.
  - Latencia y tokens.
  - Escribe `evals/report.md`.
- [ ] **6.3** `.github/workflows/evals.yml`: `workflow_dispatch` y PR que tocan `prompts/` o `evals/`.
- [ ] **6.4** `scripts/smoke.sh`: una consulta "ok" con cita y un 403 de un campo de nivel 2 sin
  permiso.

### Integración y despliegue (sesión coordinadora, requiere aprobación del usuario)

1. Merge de los WP a `main` en este orden: WP2 → WP3 → WP4 → WP5 → WP1.
2. `uv run --all-packages pytest -q` y `pnpm -C web build` en `main`.
3. **Con aprobación del usuario:** `terraform apply`, build y push de las imágenes, `scripts/ingest_local.py`,
   SWA y la prueba de humo.
4. WP6 contra la URL real. README con la arquitectura, las capturas y el enlace al reporte de
   evaluación.
