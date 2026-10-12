# Bitácora — Banco Copilot Azure

Registro de lo avanzado, iterado y fallado al construir y desplegar el copiloto. Las horas son **UTC
del 2026-10-11** y salen de los commits (`git log`), de los logs de Azure o de las salidas de las
herramientas. Cuando una hora es aproximada se marca con `~`.

> **Sobre los hashes:** el repo público se publicó con el historial limpio de identificadores del
> despliegue (ID de suscripción, tenant, sufijo de recursos y capturas que los mostraban). Por eso los
> commits a partir de `800bed5` tienen en GitHub hashes distintos de los citados acá. El mensaje y la
> hora de cada commit se conservan, así que se encuentran por su descripción.

**Estado al cierre de esta entrada:**

- En vivo en https://azure.cuisangelo.com.
- `/documentacion` está protegida con login de Microsoft, rol `owner`.
- Evaluación de 40 preguntas: **65 % de estados correctos, 0 fugas, 15/15 en seguridad**.

---

## 1. Diseño (hasta 19:50)

| Hora | Qué pasó |
|---|---|
| < 19:17 | Pedido inicial: un portfolio desplegado en Azure que cubra el temario de la formación (Foundry, Agent Framework, MCP, RAG, evaluaciones, observabilidad, guardrails, seguridad), con la cuenta Free Trial y cuidando costos. |
| < 19:17 | Suscripción revisada: `FreeTrial_2014-09-01`, límite de gasto activo, vacía. |
| < 19:17 | **Decisiones del usuario:** copiloto bancario como producto principal (primero con labs; después **un solo producto**), vida de **30 días de crédito**, todo en **español**, enfoque **A** (núcleo propio en Container Apps). |
| < 19:17 | Investigación de niveles gratuitos (subagente). **Bloqueos detectados:** APIM Consumption no aloja MCP nativo; la groundedness de Content Safety no está en F0; varias regiones de AI Search saturadas. Se elige **Canada East**. |
| < 19:17 | Registro de 14 resource providers. **Cuota real verificada:** gpt-4.1-mini 200K TPM, gpt-5-mini 500K, text-embedding-3-small 1M. |
| < 19:17 | **Decisión:** APIM Consumption con un MCP propio, en lugar de APIM Developer (unos USD 48). |
| 19:17–19:18 | Repo creado y spec v1 commiteada (`df5bc58`). |
| ~19:25 | El usuario pide una definición de producto más clara: problema del asesor, qué hace y qué no. |
| ~19:28 | El usuario pide **niveles de permiso** para acceder a datos de clientes, con aprobación de un superior. **Decisión:** personas demo simuladas, con JWT en la forma de los app roles de Entra. |
| 19:32 | Spec con §0 Producto y §0.1 Niveles de acceso 0–3 (`3ff6e36`). |
| ~19:38 | El usuario pide el frontend en **Next.js**, con estética corporativa inspirada en Interbank pero en azul y sin sus marcas. |
| 19:41 | Plan de implementación commiteado (`8012b62`). Detalle: la spec usaba nombres de campos en español; el plan los pasa a inglés por la regla de identificadores. |
| 19:43 | **Fase 0:** paquete `bank_contracts` (contratos en código, 6 tests) y workspace de uv (`a98402b`, `bdd8a99`). |

## 2. Construcción en paralelo (19:48 → 20:25)

| Hora | Qué pasó |
|---|---|
| ~19:45 | No se pudieron lanzar sesiones: el workspace no era *trusted*. El usuario aceptó el aviso. |
| ~19:48 | **5 sesiones en paralelo:** infra-terraform, data-ingest, bank-apis-mcp, copilot-api y web. |
| 19:48–19:50 | Contratos ajustados a pedido de las sesiones: `GET /access-requests/{id}`, `resume` sin body, forma plana de `customers.json`, `uv run --all-packages`. |
| ~19:58 | WP2 (data-ingest) terminado. **Verificado por el coordinador:** 38 tests, 12 documentos y 20 clientes con exactamente 9 claves. |
| ~20:00 | WP3 (bank-apis-mcp) terminado. **Mutación propia:** quitar el chequeo de `advisor_sub` pone en rojo `test_fields_with_grant_of_another_advisor_is_403`. |
| ~20:01 | Hallazgo de copilot-api: FastMCP en `0.0.0.0` **no tenía protección de Host**; aceptaba `attacker.example`. Corregido con `MCP_ALLOWED_HOSTS` (`1a5c478`). |
| ~20:02 | WP1 (infra) terminado. Plan revisado SKU por SKU: 102 recursos, Cosmos con throughput compartido de 1000 RU/s dentro del nivel gratuito. |
| 20:04 | Integración parcial: 109 tests. |
| 20:06 | `scripts/smoke.sh`, probado contra un servidor SSE falso que filtra datos (falla) y otro que no (pasa). |
| 20:12 | Dataset de 40 preguntas, con un validador contra los datos reales (mutación verificada). |
| 20:16 | Runner de evaluación con métricas deterministas y jueces de Foundry; falla con exit 1 si hay fugas. |
| 20:18 | WP5 (web): 48 tests y capturas. Se piden ids de cliente y encabezados reales en el mock. |
| 20:20 | WP4 (copilot-api) integrado: **209 tests**. **Mutación propia:** guardar el historial sin placeholder pone en rojo el test del permiso vencido. |
| 20:23 | Riesgo encontrado: el decoder de checkpoints usaba **pickle sin restricción**. Se agrega una lista de tipos permitidos (`67c5643`). |

## 3. Despliegue (20:25 → ~22:10)

| Hora | Qué pasó |
|---|---|
| ~20:22 | El usuario pide publicar en **azure.cuisangelo.com**. Se agrega el dominio y CORS cerrado a ese origen (`0566be4`). |
| ~20:24 | El **clasificador de permisos bloquea `terraform apply`**. Se escribe `scripts/deploy.sh` (9 pasos) para que lo corra el usuario. |
| 20:28 | **Intento 1 fallido.** Cosmos responde `ServiceUnavailable` por alta demanda en Canada East, y el provider rechaza `semantic_search_sku` en Search Free. |
| 20:34 | Cosmos pasa a una región variable y se quita el sku semántico (`603c29f`). |
| 20:40 | **Intento 2 fallido.** Canada Central también rechaza Cosmos. La API de Cosmos confirma `isSubscriptionRegionAccessAllowedForRegular=false` en Canada East y Canada Central: **no era saturación, era una restricción para la suscripción**. Cosmos va a **East US 2**, y el deploy chequea el acceso a la región antes de aplicar (`855612a`). Cada intento dejó una cuenta `Failed` que el usuario borró a mano. |
| 20:43 | Search Free se creó con **semántico `disabled`**. Azure acepta el plan `free`; solo lo rechaza el provider. Se activa vía `azapi` (`cae0730`). |
| ~20:55 | **Intento 3:** infra completa (37 recursos), imágenes y 12 documentos indexados. |
| 21:07 | Falla el paso 4: el host de la Function da **403 en Storage**. El provider azurerm inyecta un `AzureWebJobsStorage` con `AccountKey`, y las llaves de cuenta están deshabilitadas. Se borra en vivo, el host arranca y aparece la llave `blobs_extension` (`55ceb47`). |
| 21:12 | Smoke en vivo: groundedness responde **404 "not yet available in this region"** en Canada East, aunque la documentación lo listaba. El clasificador bloqueó un recurso de prueba. Content Safety pasa a East US 2 con un nombre nuevo, para no chocar con el soft-delete (`2e1c529`). |
| ~21:30 | **Intento 4:** pasos 1 a 5 bien. Falla el build web: faltaba `pnpm install` en el worktree (`0e662ab`). |
| ~21:50 | **Intento 5:** la web se sube y el CNAME se crea en Vercel. Falla el dominio: el **CAA** de `cuisangelo.com` no autoriza a DigiCert. El usuario pregunta si esto rompe sus otras URLs; se verifican los 6 hosts existentes y ninguno cambia. El usuario agrega `CAA 0 issue "digicert.com"`. |
| 22:04 | Prueba en vivo de toda la cadena: con `customers-api` caliente devuelve `access_required` solo por `monthly_income`. Aparecen dos bugs: el **router no veía `customer_id`** y **mcp-bank tenía un timeout de 10 s**, menor que el arranque en frío de unos 25 s (`6428c19`, `04c46bb`). |
| ~22:10 | **Intento 6: éxito.** Smoke `ok` con 5 citas y `access_required`; certificado DigiCert para `azure.cuisangelo.com`. **En vivo.** |

## 4. Calidad en vivo (22:10 → 23:25)

| Hora | Qué pasó |
|---|---|
| ~22:15 | Flujo HITL en vivo: Ana pide acceso, Sofía aprueba solo `employment_tenure_months`, la autoaprobación de Ana da 403 y la renta y la deuda no aparecen. La respuesta final queda en `insufficient`, no en `contradiction`. |
| 22:24–22:26 | Causa: el router clasifica "¿cumple…?" como `customer` y no busca documentos. El arreglo de prompt **no alcanzó** (el modelo siguió eligiendo `customer`); el arreglo estructural sí: buscar documentos también en la ruta `customer` (`4fe8a79`, `edea717`). |
| ~22:30 | El usuario reporta que **"¿Diferencia entre Oro y Platinum?" escala**, una pregunta básica. |
| 22:36 | Groundedness en modo **Summarization** marcaba 65 % de una respuesta correcta como sin sustento; en modo **QnA**, 0 %. Se cambia a QnA (`5a4190b`). |
| 22:40 | Falsa contradicción en "edad mínima" Oro contra Platinum: se agrega `subject` por producto. La ruta `product` también busca fichas (`06268d9`, `ebfb3b2`). |
| 22:43 | Top-k de 5 a 8: con 5, la búsqueda traía solo fragmentos de la Platinum (`c824507`). |
| ~22:44 | El usuario pregunta si la solución fue holística o hardcodeada. **Respuesta honesta:** cuatro arreglos de mecanismo y uno de ajuste (el top-k). |
| ~22:44 | El usuario pide `/documentacion`; después, que solo él pueda verla. Se usa auth de SWA con rol `owner` (no una contraseña en el frontend) y un server component, para que los nombres no lleguen a los chunks públicos. |
| 22:45 | **Evaluación 1:** solo 10 filas. Las primeras 9 dieron `upstream`; el runner cortó por **429 de nuestro propio rate limit**. |
| 22:46 | Causa del `upstream`: **el top-k 8 rompió Prompt Shields**, que admite como máximo 5 documentos y 10.000 caracteres por llamada (verificado contra la API). Se agrupa en lotes (`3b3d06f`). **Lección: el arreglo motivado por una sola pregunta introdujo una regresión que solo vio la evaluación completa.** |
| ~22:50 | `/documentacion` publicada. Verificado en vivo: un anónimo recibe 302 al login y 0 nombres de recurso; el certificado y las páginas públicas siguen bien. El usuario recibe su invitación al rol `owner`. |
| ~22:58 | **Evaluación 2 (línea base):** **24/40 (60 %)** y `leak_count` 1. La fuga era el texto de un fragmento envenenado, visible en la traza del inspector **pero ya descartado por Prompt Shields**; no llegó a la respuesta. |
| 23:05 | Arreglos en tres commits: |
| | - **TzInfo de pydantic** bloqueado por la lista de checkpoints: **toda reanudación tras una aprobación fallaba en producción**, y lo había introducido el arreglo de seguridad de las 20:23 (`b88e2dd`). |
| | - Contradicciones solo entre fuentes disjuntas; fragmentos bloqueados sin contenido en la traza; porcentaje de groundedness en la traza (`1ec69a1`). |
| | - Prompts con reglas generales. Se detectaron y reescribieron ejemplos copiados del dataset (sobreajuste) (`4747b2b`). |
| 23:11 | **Evaluación 3 invalidada:** se alcanzó el **tope diario de 200K tokens** (`503 token_cap`). El guardrail funcionó; el copiloto público también quedó cortado. |
| ~23:15 | **Decisión del usuario:** subir el tope a **1.000.000 tokens/día**, en la app y en `terraform.tfvars`. |
| ~23:25 | **Evaluación 4:** **26/40 (65 %)**, **0 fugas**, groundedness 4,95/5, similarity 4,21/5, **USD 0,05** las 40 preguntas. Seguridad 15/15. |
| ~23:30 | e20 a e22 reproducidos de forma aislada: **funcionan**. El error de transporte venía del rate limit en el runner, que espaciaba solo los streams. |

## 4b. Mejoras pedidas tras la cobertura (~23:40 →)

| Hora | Qué pasó |
|---|---|
| ~23:40 | Matriz de cobertura: 39 ✅ / 10 ⚠️ / 10 ❌ (`0c55eec`). El usuario aprueba 5 mejoras: GitHub público + CI, evaluaciones en Foundry, feedback humano, notebook y agentic retrieval. |
| ~23:45 | Diagrama de arquitectura cloud clicable con íconos oficiales de Azure (V24) publicado en `/documentacion`; la protección sigue verificada (302). |
| ~23:50 | Tres sesiones en paralelo: `human-feedback`, `copilot-quality` (incluye el patrón concurrente y agentic retrieval) y `evals-foundry` (incluye el notebook). |
| ~23:55 | **Decisión del usuario:** repo **público**, con el inventario de `/documentacion` fuera del código. Auditoría: el ID de suscripción, el dominio del tenant y los nombres solo aparecen en `web/app/documentacion/*` desde `800bed5`. El escaneo de secretos del historial completo sale limpio (sin llaves, tokens, SAS ni correos). El historial se limpia al final, cuando terminen las sesiones. |
| ~00:00 | El usuario pide usar "luna 6". El catálogo de Canada East tiene `gpt-6-luna` (2026-09-22, GA, chat y Responses), pero la **cuota de la Free Trial es 0 en todas las regiones** (también para `gpt-5.6-luna`). No hay precio publicado para `gpt-6-luna`. **Decisión del usuario:** seguir con gpt-4.1-mini. |

| ~00:10 | Integradas las tres sesiones. **Feedback humano:** 👍/👎 por respuesta, guardado como evento en `audit`, con una pestaña en `/supervisor`. Un `session_id` con `/` daba 500 y ahora da 422 (`f0a6509`). **Evaluaciones a Foundry y notebook** (`evals/notebooks/reporte.ipynb`). **Calidad:** respuesta sin afirmaciones → `insufficient`; perfil con nombres de producto; patrón **concurrente** con fan-out/fan-in de productos y cliente; `RETRIEVAL_MODE` requerido. 254 tests. |
| ~00:15 | **Agentic retrieval queda bloqueado:** en AI Search Free el planificador no puede llamar al modelo con identidad administrada (Microsoft exige Basic o superior), y las llaves están prohibidas por diseño. El código queda detrás de `RETRIEVAL_MODE=agentic`; se despliega con `hybrid`. |
| ~00:20 | Despliegue de `copilot-api` (revisión `--0000014`) con `RETRIEVAL_MODE=hybrid` en el mismo update; si no, la app no arranca. Web con feedback publicada. Smoke en vivo: 8 citas y `access_required`. Feedback en vivo: 201 en el caso válido y 422 con id inválido. |
| ~00:25 | El rol "Azure AI User" no existe en el tenant; se llama **"Foundry User"**. Asignado para subir evaluaciones. |
| ~00:35 | **Evaluación 5: 30/40 (75 %)**, **0 fugas**, seguridad 15/15, retrieval 4,82/5, groundedness 4,65/5, similarity 4,18/5, latencia p50 5,8 s y p95 11,5 s, **USD 0,055**. La corrida queda **registrada en Foundry → Evaluations**. Los promedios de las 4 métricas propias no se registran como agregados (el SDK pide un diccionario); los valores por fila sí. |
| ~00:40 | Clon de publicación: historial limpio de ID de suscripción, tenant, sufijo de recursos y capturas con nombres; autor reescrito a la dirección *noreply* de GitHub. 0 coincidencias; árbol idéntico al de `feat/integration`. El push lo corre el usuario. |

### Evolución de la evaluación

| Corrida | Estado correcto | Fugas | Nota |
|---|---|---|---|
| 1 | — | — | Cortada por 429 del rate limit propio; top-k 8 rompía Prompt Shields |
| 2 (línea base) | 24/40 (60 %) | 1 (falsa: traza de un fragmento descartado) | |
| 3 | — | — | Invalidada por el tope diario de tokens |
| 4 | 26/40 (65 %) | 0 | Tras TzInfo, fuentes disjuntas y prompts generales |
| 5 | **30/40 (75 %)** | **0** | Tras feedback, concurrencia y perfil con nombres; subida a Foundry |

Lo que sigue fallando (10/40): 2 de 3 contradicciones (el modelo concilia la ficha con la circular por fecha de vigencia; falta el criterio del usuario), 3 de 7 respuestas de procedimiento, 2 de 3 de perfil de cliente y 2 de 4 con permiso.

## 5. Lecciones

- **Una afirmación se gana ejecutando.** La documentación de Azure decía que groundedness existía en Canada East y que la Free Trial tenía cuotas; solo la llamada real lo resolvió, en un sentido y en el otro.
- **Probar una sola pregunta lleva a regresiones.** El top-k 8 arregló la pregunta del usuario y rompió todo lo demás. La evaluación completa es la verificación que cuenta.
- **Los arreglos de seguridad también se prueban con datos reales.** La lista de tipos de checkpoint pasó todos los tests con fechas creadas en Python, y falló con fechas leídas de Cosmos.
- **El LLM falso no ve problemas de prompt.** Seis bugs (router, búsqueda, groundedness, contradicción, top-k, minimización) solo aparecieron contra gpt-4.1-mini real.
- **Los guardrails se activan contra uno mismo.** El rate limit cortó al runner y el tope diario cortó la evaluación, y en ambos casos era lo esperado.

## 6. Pendientes conocidos

- Runner de evaluación: espaciar **todas** las llamadas, no solo los streams.
- Respuestas de "no está en la documentación" que salen como `ok`: una respuesta sin afirmaciones debería ser `insufficient`.
- Snippet del perfil del cliente con nombres de producto, no solo ids. Hoy groundedness rechaza esas respuestas (~40 %).
- **Criterio del usuario:** ficha contra circular del hipotecario. ¿El copiloto escala la contradicción (política §5) o aplica la circular por fecha de vigencia?
- `/documentacion` con diagrama cloud clicable e íconos oficiales de Azure: en curso en la sesión web-documentacion.
- Cobertura del temario: ver la matriz en `docs/cobertura.md`.
